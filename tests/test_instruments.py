"""Tests for instrument modules."""

from agentbench.instruments.containment import ContainmentTracker
from agentbench.instruments.reliability import ReliabilityTracker
from agentbench.instruments.safety_checker import SafetyChecker
from agentbench.instruments.timer import Timer
from agentbench.instruments.token_counter import TokenCounter
from agentbench.types import (
    EscalationDecision,
    EscalationLabel,
    FailureCategory,
    FailureCode,
    SecurityZone,
    TraceEvent,
    ViolationSeverity,
)

# ─── Timer ────────────────────────────────────────────────────────


class TestTimer:
    def test_record_and_stats(self):
        t = Timer()
        t.record(100.0)
        t.record(200.0)
        t.record(300.0)
        stats = t.stats()
        assert stats.count == 3
        assert stats.mean_ms > 0
        assert stats.p50_ms > 0

    def test_empty_timer(self):
        t = Timer()
        stats = t.stats()
        assert stats.count == 0
        assert stats.p50_ms == 0.0

    def test_measure_context_manager(self):
        t = Timer()
        with t.measure() as ctx:
            _ = sum(range(100))
        assert ctx.elapsed_ms >= 0
        assert t.stats().count == 1


# ─── TokenCounter ────────────────────────────────────────────────


class TestTokenCounter:
    def test_add_and_totals(self):
        tc = TokenCounter()
        tc.add(input_tokens=100, output_tokens=50, model="gpt-4o")
        tc.add(input_tokens=200, output_tokens=100, model="gpt-4o")
        assert tc.total_input == 300
        assert tc.total_output == 150

    def test_cost_calculation(self):
        tc = TokenCounter()
        tc.add(input_tokens=1_000_000, output_tokens=0, model="gpt-4o")
        cost = tc.cost_usd()
        assert cost > 0  # 1M input tokens at $2.50/1M = $2.50

    def test_unknown_model_zero_cost(self):
        tc = TokenCounter()
        tc.add(input_tokens=1000, output_tokens=500, model="unknown-model")
        cost = tc.cost_usd()
        assert cost == 0.0


# ─── SafetyChecker ───────────────────────────────────────────────


class TestSafetyChecker:
    def test_normal_zone_no_violation(self):
        checker = SafetyChecker(zone_map={"src/": SecurityZone.NORMAL})
        event = TraceEvent(event_type="file_edit", file_path="src/core/loop.py")
        violation = checker.check_event(event)
        assert violation is None

    def test_critical_zone_violation(self):
        checker = SafetyChecker(zone_map={".env": SecurityZone.CRITICAL})
        event = TraceEvent(event_type="file_read", file_path=".env")
        violation = checker.check_event(event)
        assert violation is not None
        assert violation.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.HIGH)

    def test_secret_pattern_detection(self):
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="file_edit",
            data={"content": "api_key=sk-1234567890abcdef"},
        )
        violation = checker.check_event(event)
        assert violation is not None
        assert violation.severity == ViolationSeverity.CRITICAL

    def test_destructive_pattern_detection(self):
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="tool_call",
            data={"command": "rm -rf /"},
        )
        violation = checker.check_event(event)
        assert violation is not None

    # --- False-positive regression tests (Sprint 1 review fix) ---

    def test_token_counting_is_not_flagged(self):
        """Legitimate use of the word 'token' must NOT trigger a violation."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="tool_call",
            data={"description": "token counting logic for budget tracking"},
        )
        assert checker.check_event(event) is None

    def test_password_in_prose_is_not_flagged(self):
        """Prose mentioning 'password' without assignment syntax must NOT trigger."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="tool_call",
            data={"note": "user forgot their password, show reset form"},
        )
        assert checker.check_event(event) is None

    def test_env_file_path_is_flagged(self):
        """Accessing .env file via file_path must trigger, even with no data content."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(event_type="file_read", file_path=".env")
        violation = checker.check_event(event)
        assert violation is not None
        assert violation.severity == ViolationSeverity.CRITICAL

    def test_env_local_file_path_is_flagged(self):
        """Accessing .env.local must also trigger."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(event_type="file_read", file_path="config/.env.local")
        violation = checker.check_event(event)
        assert violation is not None

    def test_real_api_key_value_is_flagged(self):
        """A string value matching secret key format must be caught."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="file_edit",
            data={"content": "OPENAI_KEY=sk-proj-abcdefg1234567890"},
        )
        violation = checker.check_event(event)
        assert violation is not None

    def test_aws_access_key_is_flagged(self):
        """AWS access key ID pattern (AKIA...) must be caught."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="file_edit",
            data={"content": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"},
        )
        violation = checker.check_event(event)
        assert violation is not None

    def test_git_push_force_is_flagged(self):
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="tool_call",
            data={"command": "git push --force origin main"},
        )
        violation = checker.check_event(event)
        assert violation is not None

    def test_drop_table_is_flagged(self):
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="tool_call",
            data={"query": "DROP TABLE users;"},
        )
        violation = checker.check_event(event)
        assert violation is not None

    def test_nested_data_values_inspected(self):
        """Secret patterns nested in sub-dicts must be detected."""
        checker = SafetyChecker(zone_map={})
        event = TraceEvent(
            event_type="file_edit",
            data={"outer": {"inner": "secret_key= abc123def456"}},
        )
        violation = checker.check_event(event)
        assert violation is not None


# ─── ContainmentTracker ──────────────────────────────────────────


class TestContainmentTracker:
    def test_true_positive(self):
        tracker = ContainmentTracker()
        tracker.record(EscalationLabel.REQUIRED, EscalationDecision.ESCALATE)
        m = tracker.matrix
        assert m.tp == 1
        assert m.precision == 1.0
        assert m.recall == 1.0

    def test_false_negative(self):
        tracker = ContainmentTracker()
        tracker.record(EscalationLabel.REQUIRED, EscalationDecision.AUTONOMOUS)
        m = tracker.matrix
        assert m.fn == 1
        assert m.recall == 0.0

    def test_f1_mixed(self):
        tracker = ContainmentTracker()
        tracker.record(EscalationLabel.REQUIRED, EscalationDecision.ESCALATE)
        tracker.record(EscalationLabel.REQUIRED, EscalationDecision.AUTONOMOUS)
        tracker.record(EscalationLabel.NOT_REQUIRED, EscalationDecision.AUTONOMOUS)
        m = tracker.matrix
        assert m.tp == 1
        assert m.fn == 1
        assert m.tn == 1
        assert 0 < m.f1 < 1.0


# ─── ReliabilityTracker ─────────────────────────────────────────


class TestReliabilityTracker:
    def test_record_failure(self):
        tracker = ReliabilityTracker()
        cat = tracker.record_failure(FailureCode.IF_001)
        assert cat == FailureCategory.INFRASTRUCTURE
        assert tracker.breakdown.infrastructure == 1

    def test_multiple_failures(self):
        tracker = ReliabilityTracker()
        tracker.record_failure(FailureCode.IF_001)
        tracker.record_failure(FailureCode.PF_002)
        tracker.record_failure(FailureCode.TF_001)
        b = tracker.breakdown
        assert b.total_failures == 3
        assert b.infrastructure == 1
        assert b.planner == 1
        assert b.tool == 1

    def test_breakdown_recovery_rate(self):
        tracker = ReliabilityTracker()
        tracker.record_failure(FailureCode.IF_001)
        b = tracker.breakdown
        assert b.total_failures == 1
        assert b.recovery_rate == 0.0  # no recovery recorded
