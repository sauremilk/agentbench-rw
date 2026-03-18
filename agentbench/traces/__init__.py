"""Trace schema — versioned JSONL format for recording and replaying agent runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agentbench.types import AgentTrace, TraceEvent, Turn

SCHEMA_VERSION = "1.0"


def trace_to_jsonl(trace: AgentTrace) -> str:
    """Serialize an AgentTrace to JSONL (one line per turn, header first)."""
    lines: list[str] = []

    # Header line
    header = {
        "_schema_version": SCHEMA_VERSION,
        "_type": "header",
        "trace_id": trace.trace_id,
        "adapter_name": trace.adapter_name,
        "scenario_name": trace.scenario_name,
        "mode": trace.mode,
        "started_at": trace.started_at,
        "finished_at": trace.finished_at,
        "success": trace.success,
        "error": trace.error,
        "metadata": trace.metadata,
    }
    lines.append(json.dumps(header, default=str))

    # One line per turn
    for turn in trace.turns:
        turn_dict = asdict(turn)
        turn_dict["_type"] = "turn"
        lines.append(json.dumps(turn_dict, default=str))

    return "\n".join(lines) + "\n"


def jsonl_to_trace(jsonl_text: str) -> AgentTrace:
    """Deserialize JSONL text back into an AgentTrace."""
    lines = [line.strip() for line in jsonl_text.strip().split("\n") if line.strip()]
    if not lines:
        msg = "Empty trace data"
        raise ValueError(msg)

    header = json.loads(lines[0])
    if header.get("_type") != "header":
        msg = "First line must be a header"
        raise ValueError(msg)

    trace = AgentTrace(
        trace_id=header["trace_id"],
        adapter_name=header.get("adapter_name", ""),
        scenario_name=header.get("scenario_name", ""),
        mode=header.get("mode", "live"),
        started_at=header.get("started_at", ""),
        finished_at=header.get("finished_at", ""),
        success=header.get("success", False),
        error=header.get("error"),
        metadata=header.get("metadata", {}),
    )

    for line in lines[1:]:
        turn_data = json.loads(line)
        if turn_data.get("_type") != "turn":
            continue

        events = [TraceEvent(**{k: v for k, v in e.items() if k != "_type"}) for e in turn_data.get("events", [])]

        turn = Turn(
            turn_id=turn_data.get("turn_id", ""),
            turn_number=turn_data.get("turn_number", 0),
            start_time=turn_data.get("start_time", ""),
            end_time=turn_data.get("end_time", ""),
            duration_ms=turn_data.get("duration_ms", 0.0),
            tokens_input=turn_data.get("tokens_input", 0),
            tokens_output=turn_data.get("tokens_output", 0),
            events=events,
            reasoning=turn_data.get("reasoning", ""),
        )
        trace.turns.append(turn)

    return trace


def save_trace(trace: AgentTrace, path: Path) -> None:
    """Save a trace to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trace_to_jsonl(trace), encoding="utf-8")


def load_trace(path: Path) -> AgentTrace:
    """Load a trace from a JSONL file."""
    return jsonl_to_trace(path.read_text(encoding="utf-8"))
