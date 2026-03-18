"""Tests for trace recording, serialization, and replay."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agentbench.traces import jsonl_to_trace, load_trace, save_trace, trace_to_jsonl
from agentbench.traces.recorder import TraceRecorder
from agentbench.traces.replayer import replay_trace
from agentbench.types import AgentTrace, RunMode, TraceEvent, Turn


class TestTraceSerializer:
    def test_roundtrip(self):
        trace = AgentTrace(adapter_name="test", scenario_name="s1")
        trace.turns.append(
            Turn(
                turn_number=1,
                start_time="t0",
                end_time="t1",
                duration_ms=100.0,
                tokens_input=500,
                tokens_output=200,
            )
        )
        trace.success = True

        jsonl = trace_to_jsonl(trace)
        restored = jsonl_to_trace(jsonl)

        assert restored.adapter_name == "test"
        assert restored.scenario_name == "s1"
        assert restored.success is True
        assert len(restored.turns) == 1
        assert restored.turns[0].tokens_input == 500

    def test_events_roundtrip(self):
        trace = AgentTrace(adapter_name="test", scenario_name="s1")
        turn = Turn(turn_number=1, start_time="t0", end_time="t1", duration_ms=50.0)
        turn.events.append(TraceEvent(event_type="file_edit", data={"path": "foo.py"}))
        trace.turns.append(turn)

        restored = jsonl_to_trace(trace_to_jsonl(trace))
        assert len(restored.turns[0].events) == 1
        assert restored.turns[0].events[0].event_type == "file_edit"

    def test_save_load_file(self):
        trace = AgentTrace(adapter_name="file-test", scenario_name="s2")
        trace.turns.append(Turn(turn_number=1, start_time="t0", end_time="t1", duration_ms=10.0))
        trace.success = True

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            save_trace(trace, path)
            loaded = load_trace(path)

        assert loaded.adapter_name == "file-test"
        assert len(loaded.turns) == 1

    def test_empty_trace_raises(self):
        try:
            jsonl_to_trace("")
            raised = False
        except ValueError:
            raised = True
        assert raised


class TestTraceRecorder:
    def test_basic_recording(self):
        rec = TraceRecorder(adapter_name="rec-test", scenario_name="s1")
        rec.start()

        with rec.turn() as t:
            t.set_tokens(input_tokens=100, output_tokens=50)
            t.add_event(TraceEvent(event_type="test_event", data={"key": "val"}))

        result = rec.finish(success=True)
        assert result.success is True
        assert len(result.turns) == 1
        assert result.turns[0].tokens_input == 100
        assert len(result.turns[0].events) == 1

    def test_multiple_turns(self):
        rec = TraceRecorder(adapter_name="multi", scenario_name="s2")
        rec.start()

        for i in range(3):
            with rec.turn() as t:
                t.set_tokens(input_tokens=100 * (i + 1))

        rec.finish(success=True)
        assert len(rec.trace.turns) == 3
        assert rec.trace.turns[0].turn_number == 1
        assert rec.trace.turns[2].turn_number == 3

    def test_save_to_file(self):
        rec = TraceRecorder(adapter_name="save", scenario_name="s3")
        rec.start()
        with rec.turn() as t:
            t.set_tokens(input_tokens=50)
        rec.finish(success=True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jsonl"
            rec.save(path)
            loaded = load_trace(path)
            assert loaded.adapter_name == "save"


class TestTraceReplay:
    def test_replay_produces_eval_result(self):
        # Build a simple trace
        trace = AgentTrace(adapter_name="replay-test", scenario_name="s1", mode=RunMode.LIVE)
        trace.turns.append(
            Turn(
                turn_number=1,
                start_time="t0",
                end_time="t1",
                duration_ms=200.0,
                tokens_input=1000,
                tokens_output=400,
            )
        )
        trace.success = True

        result = replay_trace(trace)
        assert result.trace.adapter_name == "replay-test"
        assert result.composite_score >= 0
        assert len(result.dimensions) == 7

    def test_replay_with_events(self):
        trace = AgentTrace(adapter_name="evt", scenario_name="s2")
        turn = Turn(turn_number=1, start_time="t0", end_time="t1", duration_ms=100.0, tokens_input=500)
        turn.events.append(
            TraceEvent(event_type="file_edit", data={"path": "src/core/loop.py"}, file_path="src/core/loop.py")
        )
        trace.turns.append(turn)
        trace.success = True

        result = replay_trace(trace)
        assert result.safety_gate_passed  # normal-zone file should pass
