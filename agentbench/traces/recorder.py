"""Trace recorder — records live agent runs to JSONL trace files."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentbench.traces import save_trace
from agentbench.types import (
    AgentTrace,
    RunMode,
    ToolCall,
    TraceEvent,
    Turn,
    TurnResult,
)


@dataclass
class TraceRecorder:
    """Records a live agent run into an AgentTrace.

    Usage:
        recorder = TraceRecorder(adapter_name="my_adapter", scenario_name="s1_bugfix")
        recorder.start()

        with recorder.turn() as turn:
            # ... execute agent turn ...
            turn.add_event(TraceEvent(...))
            turn.set_tokens(input=1200, output=350)

        recorder.finish(success=True)
        recorder.save(Path("results/traces/run_001.jsonl"))
    """

    adapter_name: str = ""
    scenario_name: str = ""
    _trace: AgentTrace = field(default=None, repr=False)  # type: ignore[assignment]
    _turn_counter: int = 0

    def start(self) -> None:
        """Initialize a new trace recording."""
        self._trace = AgentTrace(
            adapter_name=self.adapter_name,
            scenario_name=self.scenario_name,
            mode=RunMode.LIVE,
        )
        self._turn_counter = 0

    def turn(self) -> TurnRecordContext:
        """Context manager for recording a single turn."""
        self._turn_counter += 1
        return TurnRecordContext(self._trace, self._turn_counter)

    def add_turn_from_result(self, result: TurnResult, reasoning: str = "") -> None:
        """Add a turn directly from a TurnResult."""
        self._turn_counter += 1
        turn = Turn(
            turn_number=self._turn_counter,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            duration_ms=result.duration_ms,
            tokens_input=result.tokens_used,
            tool_calls=result.tool_calls,
            events=result.events,
            reasoning=reasoning,
        )
        self._trace.turns.append(turn)

    def finish(self, success: bool, error: str | None = None) -> AgentTrace:
        """Finalize the trace recording."""
        self._trace.finished_at = datetime.now(UTC).isoformat()
        self._trace.success = success
        self._trace.error = error
        return self._trace

    @property
    def trace(self) -> AgentTrace:
        return self._trace

    def save(self, path: Path) -> None:
        """Save the recorded trace to a JSONL file."""
        save_trace(self._trace, path)


class TurnRecordContext:
    """Context manager for recording one agent turn with timing."""

    def __init__(self, trace: AgentTrace, turn_number: int) -> None:
        self._trace = trace
        self._turn_number = turn_number
        self._events: list[TraceEvent] = []
        self._tool_calls: list[ToolCall] = []
        self._tokens_input = 0
        self._tokens_output = 0
        self._reasoning = ""
        self._start_time: float = 0.0

    def __enter__(self) -> TurnRecordContext:
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        now = datetime.now(UTC).isoformat()
        turn = Turn(
            turn_number=self._turn_number,
            start_time=now,
            end_time=now,
            duration_ms=elapsed_ms,
            tokens_input=self._tokens_input,
            tokens_output=self._tokens_output,
            tool_calls=self._tool_calls,
            events=self._events,
            reasoning=self._reasoning,
        )
        self._trace.turns.append(turn)

    def add_event(self, event: TraceEvent) -> None:
        self._events.append(event)

    def add_tool_call(self, tool_call: ToolCall) -> None:
        self._tool_calls.append(tool_call)

    def set_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self._tokens_input = input_tokens
        self._tokens_output = output_tokens

    def set_reasoning(self, reasoning: str) -> None:
        self._reasoning = reasoning
