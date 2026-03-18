# JSONL Trace Format

AgentBench-RW uses a **versioned JSONL format** for recording and replaying agent runs. One file = one evaluation run.

---

## Format Overview

Each `.jsonl` file contains:
1. **Header line** (first line) — trace metadata
2. **Turn lines** (subsequent lines) — one per agent turn

This is append-friendly and streamable: you can write turns as they happen and read the file line-by-line without loading everything into memory.

---

## Schema Version

Current: `1.0`

The header line includes `_schema_version` for forward compatibility.

---

## Header Line

```json
{
  "_schema_version": "1.0",
  "_type": "header",
  "trace_id": "uuid-string",
  "adapter_name": "orchestrator-v1",
  "scenario_name": "s1_bugfix_auth",
  "mode": "live",
  "started_at": "2026-03-15T10:30:00+00:00",
  "finished_at": "2026-03-15T10:32:15+00:00",
  "success": true,
  "error": null,
  "metadata": {}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `_schema_version` | string | Schema version for compatibility |
| `_type` | string | Always `"header"` for the first line |
| `trace_id` | string | UUID auto-generated at trace creation |
| `adapter_name` | string | Which agent adapter produced this trace |
| `scenario_name` | string | Which scenario was evaluated |
| `mode` | string | `"live"` or `"replay"` |
| `started_at` | string | ISO 8601 timestamp |
| `finished_at` | string | ISO 8601 timestamp (set at finish) |
| `success` | bool | Whether the overall task succeeded |
| `error` | string? | Error message if failed |
| `metadata` | object | Arbitrary key-value metadata |

---

## Turn Line

```json
{
  "_type": "turn",
  "turn_id": "uuid-string",
  "turn_number": 1,
  "start_time": "2026-03-15T10:30:01+00:00",
  "end_time": "2026-03-15T10:30:05+00:00",
  "duration_ms": 4200.5,
  "tokens_input": 1200,
  "tokens_output": 350,
  "tool_calls": [...],
  "events": [...],
  "reasoning": "Agent decided to fix the auth middleware..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `_type` | string | Always `"turn"` |
| `turn_id` | string | UUID per turn |
| `turn_number` | int | Sequential turn index (1-based) |
| `start_time` | string | ISO 8601 |
| `end_time` | string | ISO 8601 |
| `duration_ms` | float | Wall-clock duration in milliseconds |
| `tokens_input` | int | Input tokens consumed |
| `tokens_output` | int | Output tokens generated |
| `tool_calls` | array | List of ToolCall objects |
| `events` | array | List of TraceEvent objects |
| `reasoning` | string | Agent's reasoning (if captured) |

---

## TraceEvent Object

```json
{
  "event_type": "file_edit",
  "timestamp": "2026-03-15T10:30:03+00:00",
  "data": {"path": "src/auth.py", "lines_changed": 15},
  "file_path": "src/auth.py",
  "failure_code": null,
  "escalation_label": null,
  "escalation_decision": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | `file_edit`, `file_read`, `tool_call`, `error`, `escalation` |
| `timestamp` | string | ISO 8601 |
| `data` | object | Arbitrary event payload |
| `file_path` | string? | Affected file (for zone matching) |
| `failure_code` | string? | Failure code (e.g., `"IF-001"`) if this event is a failure |
| `escalation_label` | string? | Ground truth: should the agent have escalated? |
| `escalation_decision` | string? | What the agent actually decided |

---

## ToolCall Object

```json
{
  "tool_name": "file_edit",
  "arguments": {"path": "src/auth.py", "content": "..."},
  "result": "success",
  "duration_ms": 150.0
}
```

---

## Usage

### Save a trace

```python
from agentbench.traces import save_trace
save_trace(trace, Path("results/traces/run_001.jsonl"))
```

### Load a trace

```python
from agentbench.traces import load_trace
trace = load_trace(Path("results/traces/run_001.jsonl"))
```

### Serialize/deserialize in memory

```python
from agentbench.traces import trace_to_jsonl, jsonl_to_trace

jsonl_text = trace_to_jsonl(trace)
restored = jsonl_to_trace(jsonl_text)
```
