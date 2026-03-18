"""Runner — dual-mode evaluation engine (live + replay).

Orchestrates the full evaluation flow:
    Scenario → Adapter → Trace → Instruments → Scoring → Report
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agentbench.traces import load_trace, save_trace
from agentbench.traces.recorder import TraceRecorder
from agentbench.traces.replayer import replay_trace
from agentbench.types import EvalResult, RunMode

if TYPE_CHECKING:
    from pathlib import Path

    from agentbench.config import EvalConfig
    from agentbench.scenarios.base import BaseScenario, VerificationResult
    from agentbench.types import AgentTrace, TargetAdapter

logger = logging.getLogger(__name__)


def run_scenario(
    adapter: TargetAdapter,
    scenario: BaseScenario,
    *,
    mode: RunMode = RunMode.LIVE,
    config: EvalConfig | None = None,
    trace_dir: Path | None = None,
    trace_file: Path | None = None,
) -> RunResult:
    """Run a single scenario through an adapter and produce evaluation results.

    Args:
        adapter: The target system adapter (orchestrator, LangGraph, etc.).
        scenario: The evaluation scenario to execute.
        mode: LIVE (execute actions) or REPLAY (replay from trace file).
        config: Evaluation configuration (weights, thresholds). Uses defaults if None.
        trace_dir: Directory to save traces to (auto-named). Mutually exclusive with trace_file.
        trace_file: Specific file path for the trace. Mutually exclusive with trace_dir.

    Returns:
        RunResult with trace, eval_result, and verification.
    """
    if mode == RunMode.REPLAY:
        if not trace_file:
            msg = "trace_file required for REPLAY mode"
            raise ValueError(msg)
        return _run_replay(trace_file, scenario, config=config)

    return _run_live(adapter, scenario, config=config, trace_dir=trace_dir, trace_file=trace_file)


class RunResult:
    """Complete result from running one scenario."""

    __slots__ = ("trace", "eval_result", "verification", "scenario_name", "adapter_name")

    def __init__(
        self,
        *,
        trace: AgentTrace,
        eval_result: EvalResult,
        verification: VerificationResult,
        scenario_name: str = "",
        adapter_name: str = "",
    ) -> None:
        self.trace = trace
        self.eval_result = eval_result
        self.verification = verification
        self.scenario_name = scenario_name or trace.scenario_name
        self.adapter_name = adapter_name or trace.adapter_name

    @property
    def passed(self) -> bool:
        """Whether the scenario passed all checks."""
        return self.verification.passed and self.eval_result.safety_gate_passed

    @property
    def composite_score(self) -> float:
        return self.eval_result.composite_score

    def summary(self) -> dict[str, Any]:
        """Return a compact summary dict suitable for reporting."""
        return {
            "scenario": self.scenario_name,
            "adapter": self.adapter_name,
            "passed": self.passed,
            "composite_score": round(self.composite_score, 3),
            "safety_gate": self.eval_result.safety_gate_passed,
            "verification_passed": self.verification.passed,
            "turns": len(self.trace.turns),
            "tokens": self.trace.total_tokens,
            "duration_ms": round(self.trace.total_duration_ms, 1),
            "checks": self.verification.checks,
        }


# ---------------------------------------------------------------------------
# Live mode execution
# ---------------------------------------------------------------------------


def _run_live(
    adapter: TargetAdapter,
    scenario: BaseScenario,
    *,
    config: EvalConfig | None = None,
    trace_dir: Path | None = None,
    trace_file: Path | None = None,
) -> RunResult:
    """Execute scenario actions live against the adapter."""
    recorder = TraceRecorder(adapter_name=adapter.name, scenario_name=scenario.config.name)
    recorder.start()

    scenario.setup(adapter)
    actions = scenario.get_actions()
    all_success = True

    try:
        for action in actions:
            result = adapter.execute_turn(action)
            recorder.add_turn_from_result(result, reasoning=action.action_type)
            if not result.success:
                all_success = False
    except Exception as exc:
        logger.exception("Scenario execution failed")
        recorder.finish(success=False, error=str(exc))
        all_success = False
    else:
        recorder.finish(success=all_success)
    finally:
        scenario.teardown()
        adapter.teardown()

    trace = recorder.trace
    _save_trace(trace, trace_dir=trace_dir, trace_file=trace_file)

    eval_result = replay_trace(trace, config=config)
    verification = scenario.verify(trace)

    return RunResult(
        trace=trace,
        eval_result=eval_result,
        verification=verification,
    )


# ---------------------------------------------------------------------------
# Replay mode execution
# ---------------------------------------------------------------------------


def _run_replay(
    trace_file: Path,
    scenario: BaseScenario,
    *,
    config: EvalConfig | None = None,
) -> RunResult:
    """Replay a saved trace and re-score it (deterministic, free)."""
    trace = load_trace(trace_file)
    eval_result = replay_trace(trace, config=config)
    verification = scenario.verify(trace)

    return RunResult(
        trace=trace,
        eval_result=eval_result,
        verification=verification,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_trace(
    trace: AgentTrace,
    *,
    trace_dir: Path | None = None,
    trace_file: Path | None = None,
) -> Path | None:
    """Persist trace to disk if a path is provided."""
    if trace_file:
        save_trace(trace, trace_file)
        return trace_file
    if trace_dir:
        trace_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = trace_dir / f"{trace.adapter_name}_{trace.scenario_name}_{ts}.jsonl"
        save_trace(trace, path)
        return path
    return None
