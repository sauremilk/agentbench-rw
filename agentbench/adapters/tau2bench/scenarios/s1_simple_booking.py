"""TAU2 S1 — Simple Booking Lookup (🟢 NORMAL zone).

Pattern: Customer asks about a flight → Agent calls lookup tools → resolves.
5 turns, simple tool calls, no escalation needed.
Focus: D1 (Task Completion) + D2 (Latency) + D3 (Cost).
"""

from __future__ import annotations

from agentbench.scenarios.base import BaseScenario, VerificationResult, make_config
from agentbench.types import AgentAction, AgentTrace, ScenarioConfig

# Simulated TAU2-format conversation (airline domain, simple lookup)
_CONVERSATION_DATA = {
    "id": "airline_001",
    "domain": "airline",
    "conversations": [
        {"role": "user", "content": "Hi, I need to check the status of my flight tomorrow."},
        {
            "role": "assistant",
            "content": "I'd be happy to help! Could you share your booking reference?",
        },
        {"role": "user", "content": "Sure, it's FLT-7890."},
        {
            "role": "tool_call",
            "tool": "get_booking",
            "args": {"reference": "FLT-7890"},
        },
        {
            "role": "tool_result",
            "tool": "get_booking",
            "result": '{"flight": "AA123", "date": "2025-03-15", "status": "on_time", "gate": "B22"}',
        },
        {
            "role": "assistant",
            "content": (
                "Your flight AA123 on March 15 is on time. You'll be departing from gate B22. Is there anything else?"
            ),
        },
        {"role": "user", "content": "No, that's all. Thanks!"},
        {"role": "assistant", "content": "You're welcome! Have a great flight."},
    ],
    "tools": [
        {"name": "get_booking", "description": "Look up flight booking by reference number"},
    ],
    "expected_actions": ["get_booking"],
    "expected_outcome": "booking_status_provided",
    "resolved": True,
}


class S1SimpleBooking(BaseScenario):
    """TAU2-Bench simple booking lookup — replay 5 turns, 🟢 NORMAL zone."""

    @property
    def config(self) -> ScenarioConfig:
        return make_config(
            name="tau2_s1_simple_booking",
            description=(
                "TAU2-Bench replay: Customer asks about flight status. "
                "Agent looks up booking via get_booking tool and provides info. "
                "🟢 NORMAL zone, no escalation, 5 turns."
            ),
            adapter_name="tau2bench",
            expected_files=[],
            ground_truth={},
            inject={
                "conversation": _CONVERSATION_DATA,
                "tool_zone_map": {
                    "get_booking": "normal",
                },
            },
            timeout=30.0,
        )

    def get_actions(self) -> list[AgentAction]:
        # One action per expected conversation turn for the replayer
        return [AgentAction(action_type="replay_turn", arguments={"turn": i}) for i in range(1, 6)]

    def verify(self, trace: AgentTrace) -> VerificationResult:
        checks: dict[str, bool] = {}
        notes: list[str] = []

        # Check 1: Trace completed successfully
        checks["trace_success"] = trace.success

        # Check 2: Reasonable number of turns (5+ replay turns)
        checks["has_turns"] = len(trace.turns) >= 4
        if not checks["has_turns"]:
            notes.append(f"Expected ≥4 turns, got {len(trace.turns)}")

        # Check 3: At least one tool call (get_booking)
        tool_events = [e for e in trace.all_events if e.event_type == "tool_call"]
        checks["has_tool_call"] = len(tool_events) >= 1

        # Check 4: No escalation events (simple task)
        esc_events = [e for e in trace.all_events if e.event_type == "escalation"]
        checks["no_escalation"] = len(esc_events) == 0

        # Check 5: Expected tool was used
        tool_names = {tc.tool_name for t in trace.turns for tc in t.tool_calls}
        checks["correct_tool"] = "get_booking" in tool_names
        if not checks["correct_tool"]:
            notes.append(f"Expected get_booking tool, got {tool_names}")

        return VerificationResult(passed=all(checks.values()), checks=checks, notes=notes)
