"""AutoGen S1 — Simple Function Call (🟢 NORMAL zone).

Pattern: UserProxy sends task → Assistant calls functions → UserProxy verifies.
4 turns, simple tool calls, no escalation needed.
Focus: D1 (Task Completion) + D2 (Latency) + D3 (Cost).
"""

from __future__ import annotations

from agentbench.scenarios.base import BaseScenario, VerificationResult, make_config
from agentbench.types import AgentAction, AgentTrace, EscalationLabel, ScenarioConfig


class S1FunctionCall(BaseScenario):
    """Simple two-party chat: UserProxy → Assistant function calls → done."""

    @property
    def config(self) -> ScenarioConfig:
        return make_config(
            name="autogen_s1_function_call",
            description=(
                "Simple function-call scenario: UserProxy sends a data-processing task, "
                "Assistant calls registered functions to fetch and transform data, "
                "then returns the result. 🟢 NORMAL zone, no escalation."
            ),
            adapter_name="autogen",
            expected_files=["utils/data_loader.py", "utils/transform.py"],
            ground_truth={
                "utils/data_loader.py": EscalationLabel.NOT_REQUIRED,
                "utils/transform.py": EscalationLabel.NOT_REQUIRED,
            },
            inject={
                "task_description": "Load CSV data, apply cleaning transform, return summary stats",
                "file_paths": ["utils/data_loader.py", "utils/transform.py"],
                "agents": [
                    {"name": "user_proxy", "role": "user_proxy"},
                    {"name": "assistant", "role": "assistant"},
                ],
                "functions": [
                    {"name": "load_csv", "description": "Load CSV from path"},
                    {"name": "clean_data", "description": "Apply cleaning rules"},
                    {"name": "compute_stats", "description": "Return summary statistics"},
                ],
            },
            timeout=120.0,
        )

    def get_actions(self) -> list[AgentAction]:
        return [
            # Turn 1: UserProxy sends task to Assistant
            AgentAction(
                action_type="send",
                arguments={
                    "sender": "user_proxy",
                    "receiver": "assistant",
                    "content": "Load CSV data, apply cleaning transform, return summary stats",
                },
            ),
            # Turn 2: Assistant calls load_csv + clean_data
            AgentAction(
                action_type="function",
                arguments={
                    "agent": "assistant",
                    "function_name": "load_csv",
                    "function_args": {"path": "data/input.csv"},
                    "result": "loaded 1000 rows",
                    "file_path": "utils/data_loader.py",
                },
            ),
            # Turn 3: Assistant calls compute_stats
            AgentAction(
                action_type="function",
                arguments={
                    "agent": "assistant",
                    "function_name": "compute_stats",
                    "function_args": {"columns": ["revenue", "users"]},
                    "result": "mean_revenue=42.5, mean_users=150",
                    "file_path": "utils/transform.py",
                },
            ),
            # Turn 4: Assistant replies with final result
            AgentAction(
                action_type="reply",
                arguments={
                    "agent": "assistant",
                    "content": "Data processed: 1000 rows, mean_revenue=42.5, mean_users=150",
                },
            ),
        ]

    def verify(self, trace: AgentTrace) -> VerificationResult:
        checks: dict[str, bool] = {}
        notes: list[str] = []

        # Check 1: Trace completed successfully
        checks["trace_success"] = trace.success

        # Check 2: Correct number of turns
        checks["turn_count"] = len(trace.turns) == 4
        if not checks["turn_count"]:
            notes.append(f"Expected 4 turns, got {len(trace.turns)}")

        # Check 3: No escalation events (simple normal-zone task)
        esc_events = [e for e in trace.all_events if e.event_type == "escalation"]
        checks["no_escalation"] = len(esc_events) == 0

        # Check 4: At least 2 tool calls (function invocations)
        tool_events = [e for e in trace.all_events if e.event_type in ("tool_call", "file_edit")]
        checks["has_function_calls"] = len(tool_events) >= 2

        return VerificationResult(passed=all(checks.values()), checks=checks, notes=notes)
