"""Tests for Phase 3 — TunedPolicy v2, optimizer, CLI, and comparison reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.scenarios.s1_bugfix import S1SoloBugfix
from agentbench.policies.escalation import RuleBasedPolicy, TunedPolicy
from agentbench.policies.optimizer import OptimizerResult, PolicyVariant, grid_search, quick_compare
from agentbench.report.generator import generate_comparison_report, generate_run_report
from agentbench.runner import RunResult, run_scenario
from agentbench.types import AgentTrace, EscalationDecision, SecurityZone, TurnContext

if TYPE_CHECKING:
    from pathlib import Path


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_trace() -> AgentTrace:
    """Run S1 live and return the trace."""
    adapter = OrchestratorAdapter()
    scenario = S1SoloBugfix()
    result = run_scenario(adapter, scenario)
    return result.trace


def _make_run_result() -> RunResult:
    """Run S1 live and return the full RunResult."""
    adapter = OrchestratorAdapter()
    scenario = S1SoloBugfix()
    return run_scenario(adapter, scenario)


# =========================================================================
# TunedPolicy v2
# =========================================================================


class TestTunedPolicy:
    """Tests for the optimized TunedPolicy v2."""

    def test_name(self) -> None:
        assert TunedPolicy().name == "tuned-v2"

    def test_critical_always_escalates(self) -> None:
        policy = TunedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.CRITICAL)
        result = policy.evaluate(ctx)
        assert result.should_escalate
        assert any("critical" in r.lower() for r in result.reasons)

    def test_sensitive_high_confidence_continues(self) -> None:
        """Key v2 change: SENSITIVE + high confidence → no escalation (unlike v1)."""
        policy = TunedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE, confidence=0.9)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_sensitive_low_confidence_escalates(self) -> None:
        """SENSITIVE + low confidence → escalate."""
        policy = TunedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE, confidence=0.2)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_normal_high_confidence_continues(self) -> None:
        policy = TunedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.NORMAL, confidence=0.9)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_normal_low_confidence_escalates(self) -> None:
        policy = TunedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.NORMAL, confidence=0.2)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_confidence_at_threshold_continues(self) -> None:
        """Confidence exactly at threshold should NOT escalate (>=, not >)."""
        policy = TunedPolicy(min_confidence=0.45)
        ctx = TurnContext(security_zone=SecurityZone.NORMAL, confidence=0.45)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_excessive_retries_escalate(self) -> None:
        policy = TunedPolicy()
        ctx = TurnContext(retry_count=5)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_budget_overrun_tighter(self) -> None:
        """Budget multiplier is 1.2x (tighter than v1's 1.5x)."""
        policy = TunedPolicy()
        # 1.3x budget should trigger (> 1.2x)
        ctx = TurnContext(tokens_used=65_000, token_budget=50_000)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_custom_thresholds(self) -> None:
        policy = TunedPolicy(min_confidence=0.8, budget_multiplier=2.0, max_retries=5)
        ctx = TurnContext(confidence=0.5, security_zone=SecurityZone.NORMAL)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_v2_vs_v1_sensitive_delta(self) -> None:
        """V2 should NOT escalate SENSITIVE+high-confidence; V1 should."""
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE, confidence=0.9)
        v1 = RuleBasedPolicy()
        v2 = TunedPolicy()
        assert v1.should_escalate(ctx) == EscalationDecision.ESCALATE
        assert v2.should_escalate(ctx) == EscalationDecision.AUTONOMOUS


# =========================================================================
# Optimizer
# =========================================================================


class TestOptimizer:
    """Tests for grid_search and quick_compare."""

    def test_quick_compare_returns_3_variants(self) -> None:
        traces = [_make_trace()]
        result = quick_compare(traces)
        assert isinstance(result, OptimizerResult)
        assert result.baseline_null is not None
        assert result.baseline_v1 is not None
        assert len(result.variants) == 1  # v2 only
        assert result.best_variant is result.variants[0]

    def test_quick_compare_names(self) -> None:
        traces = [_make_trace()]
        result = quick_compare(traces)
        assert result.baseline_null is not None
        assert result.baseline_v1 is not None
        assert result.baseline_null.name == "null-v0"
        assert result.baseline_v1.name == "rule-based-v1"
        assert "tuned" in result.best_variant.name

    def test_grid_search_basic(self) -> None:
        traces = [_make_trace()]
        result = grid_search(
            traces,
            confidence_grid=[0.3, 0.45],
            budget_grid=[1.2],
            retry_grid=[2],
            include_baselines=True,
        )
        assert len(result.variants) == 2  # 2 confidence × 1 budget × 1 retry
        assert result.baseline_null is not None
        assert result.baseline_v1 is not None
        assert result.best_f1 >= 0.0

    def test_grid_search_no_baselines(self) -> None:
        traces = [_make_trace()]
        result = grid_search(
            traces,
            confidence_grid=[0.45],
            budget_grid=[1.2],
            retry_grid=[2],
            include_baselines=False,
        )
        assert result.baseline_null is None
        assert result.baseline_v1 is None
        assert len(result.variants) == 1

    def test_comparison_table_markdown(self) -> None:
        traces = [_make_trace()]
        result = quick_compare(traces)
        table = result.comparison_table()
        assert "| Variant" in table
        assert "null-v0" in table
        assert "rule-based-v1" in table
        assert "BEST" in table

    def test_policy_variant_metrics(self) -> None:
        variant = PolicyVariant(name="test", params={"x": 1})
        assert variant.mean_f1 == 0.0
        assert variant.mean_composite == 0.0
        assert variant.safety_pass_rate == 0.0


# =========================================================================
# Comparison reports
# =========================================================================


class TestComparisonReport:
    """Tests for generate_run_report and generate_comparison_report."""

    def test_run_report_contains_scenario(self) -> None:
        result = _make_run_result()
        report = generate_run_report(result)
        assert "orchestrator_s1_solo_bugfix" in report
        assert "orchestrator" in report

    def test_run_report_contains_verification(self) -> None:
        result = _make_run_result()
        report = generate_run_report(result)
        assert "Verification" in report

    def test_comparison_report_multi_run(self) -> None:
        results = [_make_run_result(), _make_run_result()]
        report = generate_comparison_report(
            results,
            title="Test Compare",
            labels=["run-a", "run-b"],
        )
        assert "Test Compare" in report
        assert "run-a" in report
        assert "run-b" in report
        assert "Summary" in report


# =========================================================================
# CLI
# =========================================================================


class TestCLI:
    """Tests for CLI argument parsing and commands."""

    def test_list_scenarios(self, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main

        main(["list", "--scenarios"])
        out = capsys.readouterr().out
        assert "Scenarios" in out

    def test_list_adapters(self, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main

        main(["list", "--adapters"])
        out = capsys.readouterr().out
        assert "orchestrator" in out
        assert "langgraph" in out

    def test_list_policies(self, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main

        main(["list", "--policies"])
        out = capsys.readouterr().out
        assert "null" in out
        assert "tuned" in out

    def test_run_live(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main

        rc = main(
            [
                "run",
                "--adapter",
                "orchestrator",
                "--scenario",
                "orchestrator_s1_solo_bugfix",
                "--output-dir",
                str(tmp_path),
            ]
        )
        out = capsys.readouterr().out
        assert "orchestrator_s1_solo_bugfix" in out
        assert rc in (0, 1)  # may pass or fail depending on scenario

    def test_run_with_report(self, tmp_path: Path) -> None:
        from agentbench.cli import main

        main(
            [
                "run",
                "--adapter",
                "orchestrator",
                "--scenario",
                "orchestrator_s1_solo_bugfix",
                "--output-dir",
                str(tmp_path),
                "--report",
            ]
        )
        reports = list(tmp_path.glob("*_report.md"))
        assert len(reports) >= 1

    def test_report_from_trace(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main
        from agentbench.traces import save_trace

        trace = _make_trace()
        trace_path = tmp_path / "test.jsonl"
        save_trace(trace, trace_path)

        output_path = tmp_path / "report.md"
        main(["report", "--trace", str(trace_path), "--output", str(output_path)])
        assert output_path.exists()

    def test_optimize(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from agentbench.cli import main
        from agentbench.traces import save_trace

        trace = _make_trace()
        trace_dir = tmp_path / "traces"
        trace_dir.mkdir()
        save_trace(trace, trace_dir / "s1.jsonl")

        output = tmp_path / "opt.md"
        rc = main(["optimize", "--traces-dir", str(trace_dir), "--output", str(output)])
        assert rc == 0
        assert output.exists()
        out = capsys.readouterr().out
        assert "Best" in out

    def test_unknown_scenario_fails(self) -> None:
        from agentbench.cli import main

        with pytest.raises(KeyError, match="nonexistent"):
            main(["run", "--adapter", "orchestrator", "--scenario", "nonexistent"])

    def test_no_command_fails(self) -> None:
        from agentbench.cli import main

        with pytest.raises(SystemExit):
            main([])
