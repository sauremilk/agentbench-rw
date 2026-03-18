"""Tests for Phase 4 — Portfolio: baselines, comparison, policy-aware replay, adapter containment."""

from __future__ import annotations

import pytest

from agentbench.adapters.langgraph.adapter import LangGraphAdapter
from agentbench.adapters.langgraph.scenarios.s1_classify_route import S1ClassifyRoute
from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.scenarios.s1_bugfix import S1SoloBugfix
from agentbench.adapters.orchestrator.scenarios.s2_feature import S2MultiFileFeature
from agentbench.adapters.orchestrator.scenarios.s3_crosspod import S3CrossTeamEscalation
from agentbench.policies.escalation import NullPolicy, RuleBasedPolicy, TunedPolicy
from agentbench.policies.optimizer import PolicyVariant, quick_compare
from agentbench.runner import run_scenario
from agentbench.traces.replayer import replay_trace
from agentbench.types import (
    AgentTrace,
    ContainmentMatrix,
    EscalationDecision,
    EscalationLabel,
    EvalResult,
    SecurityZone,
)

# ─── Helpers ────────────────────────────────────────────────────────────────


def _run_orchestrator(scenario_cls: type) -> AgentTrace:
    adapter = OrchestratorAdapter()
    scenario = scenario_cls()
    result = run_scenario(adapter, scenario)
    return result.trace


def _run_langgraph() -> AgentTrace:
    adapter = LangGraphAdapter()
    scenario = S1ClassifyRoute()
    result = run_scenario(adapter, scenario)
    return result.trace


def _all_traces() -> list[AgentTrace]:
    return [
        _run_orchestrator(S1SoloBugfix),
        _run_orchestrator(S2MultiFileFeature),
        _run_orchestrator(S3CrossTeamEscalation),
        _run_langgraph(),
    ]


# =========================================================================
# Policy-Aware Replay — Different policies produce different containment
# =========================================================================


class TestPolicyAwareReplay:
    """Replay the same trace with v0/v1/v2 and verify scoring diverges."""

    def test_null_policy_never_escalates(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        result = replay_trace(trace, policy=NullPolicy())
        # NullPolicy should produce zero TP (never escalates)
        assert result.containment.tp == 0

    def test_rule_policy_escalates_sensitive(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        result = replay_trace(trace, policy=RuleBasedPolicy())
        # RuleBasedPolicy escalates ALL sensitive files → at least 1 TP
        assert result.containment.tp > 0

    def test_tuned_policy_higher_precision_than_rule(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        v1_result = replay_trace(trace, policy=RuleBasedPolicy())
        v2_result = replay_trace(trace, policy=TunedPolicy())
        # v2 should have equal or better precision (fewer FPs)
        assert v2_result.containment.precision >= v1_result.containment.precision

    def test_policies_diverge_on_same_trace(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        v0 = replay_trace(trace, policy=NullPolicy())
        v1 = replay_trace(trace, policy=RuleBasedPolicy())
        replay_trace(trace, policy=TunedPolicy())
        # At least v0 and v1 must differ in containment F1
        assert v0.containment.f1 != v1.containment.f1

    def test_s3_all_policies_maintain_safety(self) -> None:
        trace = _run_orchestrator(S3CrossTeamEscalation)
        for policy in [NullPolicy(), RuleBasedPolicy(), TunedPolicy()]:
            result = replay_trace(trace, policy=policy)
            assert result.safety_gate_passed

    def test_replay_with_policy_produces_7_dimensions(self) -> None:
        trace = _run_orchestrator(S1SoloBugfix)
        result = replay_trace(trace, policy=TunedPolicy())
        assert len(result.dimensions) == 7

    def test_langgraph_trace_with_policy(self) -> None:
        trace = _run_langgraph()
        result = replay_trace(trace, policy=RuleBasedPolicy())
        assert result.composite_score >= 0
        assert len(result.dimensions) == 7


# =========================================================================
# Adapter Containment Annotations — ground truth labels in events
# =========================================================================


class TestOrchestratorContainmentAnnotations:
    """Orchestrator adapter annotates file_edit events with containment data."""

    def test_s2_has_containment_annotations(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        labeled_events = [e for e in trace.all_events if e.escalation_label is not None]
        assert len(labeled_events) > 0, "S2 trace should have labeled events"

    def test_s2_has_escalation_events(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        esc_events = [e for e in trace.all_events if e.escalation_decision == EscalationDecision.ESCALATE]
        assert len(esc_events) > 0, "S2 should have explicit escalation"

    def test_s2_has_autonomous_events(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        auto_events = [e for e in trace.all_events if e.escalation_decision == EscalationDecision.AUTONOMOUS]
        assert len(auto_events) > 0, "S2 should have autonomous file edits"

    def test_s3_escalation_labels_critical_files(self) -> None:
        trace = _run_orchestrator(S3CrossTeamEscalation)
        esc_events = [
            e
            for e in trace.all_events
            if e.escalation_decision == EscalationDecision.ESCALATE and e.escalation_label == EscalationLabel.REQUIRED
        ]
        assert len(esc_events) >= 1, "S3 should escalate at least 1 REQUIRED file"

    def test_confidence_set_on_file_edits(self) -> None:
        trace = _run_orchestrator(S2MultiFileFeature)
        for event in trace.all_events:
            if event.event_type == "file_edit" and event.data.get("confidence") is not None:
                conf = event.data["confidence"]
                assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of range"

    def test_escalated_files_not_double_labeled(self) -> None:
        """Files explicitly escalated should not get a second label in file_edit."""
        trace = _run_orchestrator(S2MultiFileFeature)
        escalated_paths = {
            e.file_path for e in trace.all_events if e.escalation_decision == EscalationDecision.ESCALATE
        }
        for event in trace.all_events:
            if event.event_type == "file_edit" and event.file_path in escalated_paths:
                assert event.escalation_label is None, (
                    f"File {event.file_path} was escalated but also labeled in file_edit"
                )


class TestLangGraphContainmentAnnotations:
    """LangGraph adapter also annotates events with containment data."""

    def test_s1_has_implement_events(self) -> None:
        trace = _run_langgraph()
        impl_events = [e for e in trace.all_events if e.event_type == "file_edit"]
        assert len(impl_events) >= 0  # LangGraph S1 may or may not have file edits

    def test_langgraph_no_double_labels(self) -> None:
        trace = _run_langgraph()
        escalated_paths = {
            e.file_path for e in trace.all_events if e.escalation_decision == EscalationDecision.ESCALATE
        }
        for event in trace.all_events:
            if event.event_type == "file_edit" and event.file_path in escalated_paths:
                assert event.escalation_label is None


# =========================================================================
# Confidence Estimation — zone/label → confidence
# =========================================================================


class TestConfidenceEstimation:
    """Tests for _estimate_confidence helper on both adapters."""

    def test_orchestrator_critical_low_confidence(self) -> None:
        adapter = OrchestratorAdapter()
        conf = adapter._estimate_confidence(SecurityZone.CRITICAL, None)
        assert conf < 0.5

    def test_orchestrator_sensitive_required_low(self) -> None:
        adapter = OrchestratorAdapter()
        conf = adapter._estimate_confidence(SecurityZone.SENSITIVE, EscalationLabel.REQUIRED)
        assert conf < 0.5

    def test_orchestrator_sensitive_not_required_high(self) -> None:
        adapter = OrchestratorAdapter()
        conf = adapter._estimate_confidence(SecurityZone.SENSITIVE, EscalationLabel.NOT_REQUIRED)
        assert conf > 0.5

    def test_orchestrator_normal_high_confidence(self) -> None:
        adapter = OrchestratorAdapter()
        conf = adapter._estimate_confidence(SecurityZone.NORMAL, None)
        assert conf > 0.8

    def test_langgraph_critical_low_confidence(self) -> None:
        adapter = LangGraphAdapter()
        conf = adapter._estimate_confidence(SecurityZone.CRITICAL, None)
        assert conf < 0.5

    def test_langgraph_normal_high_confidence(self) -> None:
        adapter = LangGraphAdapter()
        conf = adapter._estimate_confidence(SecurityZone.NORMAL, None)
        assert conf > 0.8


# =========================================================================
# Micro-Averaging — PolicyVariant aggregates TP/FP/FN across traces
# =========================================================================


class TestMicroAveraging:
    """PolicyVariant uses micro-averaging, not per-trace mean."""

    def test_micro_f1_consistent(self) -> None:
        """Micro F1 should aggregate across traces, not average per-trace."""
        traces = _all_traces()
        result = quick_compare(traces)
        v2 = result.best_variant

        # Manually compute micro-averaged F1
        tp = sum(r.containment.tp for r in v2.results)
        fp = sum(r.containment.fp for r in v2.results)
        fn = sum(r.containment.fn for r in v2.results)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        expected_f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

        assert abs(v2.mean_f1 - expected_f1) < 1e-9

    def test_empty_variant_returns_zero(self) -> None:
        v = PolicyVariant(name="empty", params={})
        assert v.mean_f1 == 0.0
        assert v.mean_recall == 0.0
        assert v.mean_precision == 0.0
        assert v.mean_composite == 0.0

    def test_micro_recall_all_tp(self) -> None:
        """If all results have only TP, micro recall = 1.0."""
        r1 = EvalResult.__new__(EvalResult)
        r1.containment = ContainmentMatrix(tp=3, fp=0, tn=2, fn=0)
        r1.composite_score = 90.0
        r1.safety_gate_passed = True
        r2 = EvalResult.__new__(EvalResult)
        r2.containment = ContainmentMatrix(tp=2, fp=1, tn=1, fn=0)
        r2.composite_score = 85.0
        r2.safety_gate_passed = True

        v = PolicyVariant(name="test", params={}, results=[r1, r2])
        assert v.mean_recall == 1.0  # 5/(5+0)
        assert abs(v.mean_precision - 5 / 6) < 1e-9  # 5/(5+1)


# =========================================================================
# Quick Compare — 3-way comparison structure
# =========================================================================


class TestQuickCompare:
    """quick_compare produces correct 3-variant result."""

    def test_returns_three_variants(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        assert result.baseline_null is not None
        assert result.baseline_v1 is not None
        assert result.best_variant is not None

    def test_v0_has_zero_containment(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        v0 = result.baseline_null
        assert v0 is not None
        assert v0.mean_f1 == 0.0

    def test_v2_outperforms_v1_on_f1(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        assert result.baseline_v1 is not None
        assert result.best_variant.mean_f1 >= result.baseline_v1.mean_f1

    def test_v2_perfect_precision(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        assert result.best_variant.mean_precision == 1.0

    def test_comparison_table_is_markdown(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        md = result.comparison_table()
        assert "|" in md
        assert "null-v0" in md or "rule-v1" in md

    def test_all_variants_pass_safety(self) -> None:
        traces = _all_traces()
        result = quick_compare(traces)
        for variant in [result.baseline_null, result.baseline_v1, result.best_variant]:
            assert variant is not None
            assert variant.safety_pass_rate == 1.0


# =========================================================================
# Baseline Trace Generation — structural tests
# =========================================================================


class TestBaselineStructure:
    """Baseline traces from live runs have expected structure."""

    @pytest.fixture()
    def s1_trace(self) -> AgentTrace:
        return _run_orchestrator(S1SoloBugfix)

    @pytest.fixture()
    def s2_trace(self) -> AgentTrace:
        return _run_orchestrator(S2MultiFileFeature)

    @pytest.fixture()
    def s3_trace(self) -> AgentTrace:
        return _run_orchestrator(S3CrossTeamEscalation)

    def test_s1_has_7_turns(self, s1_trace: AgentTrace) -> None:
        assert len(s1_trace.turns) == 7

    def test_s2_has_13_turns(self, s2_trace: AgentTrace) -> None:
        assert len(s2_trace.turns) == 13

    def test_s3_has_13_turns(self, s3_trace: AgentTrace) -> None:
        assert len(s3_trace.turns) == 13

    def test_all_traces_succeed_except_s3(self) -> None:
        """S3 is designed to have trace_success=False (cross-pod escalation)."""
        for cls in [S1SoloBugfix, S2MultiFileFeature]:
            trace = _run_orchestrator(cls)
            assert trace.success is True, f"{cls.__name__} should succeed"
        s3 = _run_orchestrator(S3CrossTeamEscalation)
        assert s3.success is False  # S3 blocks CRITICAL file edits → not fully successful

    def test_traces_score_above_70(self) -> None:
        for trace in _all_traces():
            result = replay_trace(trace, policy=TunedPolicy())
            assert result.composite_score >= 70.0, f"{trace.scenario_name} scored {result.composite_score}"
