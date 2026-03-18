"""Tests for Phase 2 runner — live and replay modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agentbench.adapters.langgraph.adapter import LangGraphAdapter
from agentbench.adapters.langgraph.scenarios.s1_classify_route import S1ClassifyRoute
from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.scenarios.s1_bugfix import S1SoloBugfix
from agentbench.runner import RunResult, run_scenario
from agentbench.types import RunMode

# =========================================================================
# Live mode — Orchestrator
# =========================================================================


class TestRunnerLiveOrchestrator:
    def test_run_orchestrator_s1_live(self) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        result = run_scenario(adapter, scenario, mode=RunMode.LIVE)

        assert isinstance(result, RunResult)
        assert isinstance(result.composite_score, float)
        assert result.scenario_name == "orchestrator_s1_solo_bugfix"
        assert result.adapter_name == "orchestrator"
        assert len(result.trace.turns) >= 5

    def test_run_orchestrator_s1_verification(self) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        result = run_scenario(adapter, scenario)

        assert result.verification.passed is not None
        assert "trace_success" in result.verification.checks

    def test_run_orchestrator_s1_summary(self) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        result = run_scenario(adapter, scenario)
        summary = result.summary()

        assert "scenario" in summary
        assert "composite_score" in summary
        assert "safety_gate" in summary
        assert "turns" in summary
        assert summary["adapter"] == "orchestrator"

    def test_run_with_trace_file(self, tmp_path: Path) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        trace_path = tmp_path / "test_trace.jsonl"
        result = run_scenario(adapter, scenario, trace_file=trace_path)

        assert trace_path.exists()
        assert result.trace.turns

    def test_run_with_trace_dir(self, tmp_path: Path) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        run_scenario(adapter, scenario, trace_dir=tmp_path)

        # Should have created a file in the directory
        trace_files = list(tmp_path.glob("*.jsonl"))
        assert len(trace_files) == 1


# =========================================================================
# Live mode — LangGraph
# =========================================================================


class TestRunnerLiveLangGraph:
    def test_run_langgraph_s1_live(self) -> None:
        adapter = LangGraphAdapter()
        scenario = S1ClassifyRoute()
        result = run_scenario(adapter, scenario, mode=RunMode.LIVE)

        assert isinstance(result, RunResult)
        assert result.scenario_name == "langgraph_s1_classify_route"
        assert result.adapter_name == "langgraph"
        assert len(result.trace.turns) == 4


# =========================================================================
# Replay mode
# =========================================================================


class TestRunnerReplay:
    def test_replay_from_trace_file(self, tmp_path: Path) -> None:
        # First: produce a trace via live run
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        trace_path = tmp_path / "replay_test.jsonl"
        live_result = run_scenario(adapter, scenario, trace_file=trace_path)

        # Then: replay it
        replay_result = run_scenario(
            adapter,  # adapter ignored in replay mode
            scenario,
            mode=RunMode.REPLAY,
            trace_file=trace_path,
        )

        assert isinstance(replay_result, RunResult)
        assert replay_result.composite_score >= 0
        # Replay should produce same number of turns
        assert len(replay_result.trace.turns) == len(live_result.trace.turns)

    def test_replay_requires_trace_file(self) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        with pytest.raises(ValueError, match="trace_file required"):
            run_scenario(adapter, scenario, mode=RunMode.REPLAY)

    def test_replay_deterministic(self, tmp_path: Path) -> None:
        """Two replays of the same trace yield the same composite score."""
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        trace_path = tmp_path / "deterministic.jsonl"
        run_scenario(adapter, scenario, trace_file=trace_path)

        r1 = run_scenario(adapter, scenario, mode=RunMode.REPLAY, trace_file=trace_path)
        r2 = run_scenario(adapter, scenario, mode=RunMode.REPLAY, trace_file=trace_path)

        assert r1.composite_score == r2.composite_score


# =========================================================================
# RunResult
# =========================================================================


class TestRunResult:
    def test_passed_property(self) -> None:
        adapter = OrchestratorAdapter()
        scenario = S1SoloBugfix()
        result = run_scenario(adapter, scenario)
        # passed is bool
        assert isinstance(result.passed, bool)
