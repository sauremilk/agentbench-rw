"""TAU2-Bench format converter — maps TAU2-Bench conversations to AgentBench traces.

TAU2-Bench (Sierra Research) records User↔Agent↔Tool interactions in a
structured JSON format.  This module converts those conversations into
AgentBench ``AgentTrace`` objects so they can be re-scored with the 7-D
evaluation engine.

TAU2-Bench input schema (simplified)::

    {
        "id": "airline_001",
        "domain": "airline",
        "conversations": [
            {"role": "user", "content": "I need to cancel my flight"},
            {"role": "assistant", "content": "Looking up your booking..."},
            {"role": "tool_call", "tool": "get_booking", "args": {"ref": "ABC123"}},
            {"role": "tool_result", "tool": "get_booking", "result": "..."},
            {"role": "assistant", "content": "I found your booking..."},
            {"role": "transfer", "target": "human_agent"}
        ],
        "tools": [
            {"name": "get_booking", "description": "Retrieve booking by reference"}
        ],
        "expected_actions": ["get_booking", "cancel_booking"],
        "expected_outcome": "booking_cancelled",
        "resolved": true
    }
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentbench.types import (
    AgentTrace,
    EscalationDecision,
    EscalationLabel,
    RunMode,
    SecurityZone,
    ToolCall,
    TraceEvent,
    Turn,
)


def convert_tau2_conversation(
    conversation_data: dict[str, Any],
    *,
    zone_map: dict[str, str] | None = None,
) -> AgentTrace:
    """Convert a single TAU2-Bench conversation record into an AgentTrace.

    Args:
        conversation_data: A TAU2-Bench conversation dict with ``conversations``,
            ``tools``, ``expected_actions``, etc.
        zone_map: Optional mapping of tool names → security zone strings.

    Returns:
        An ``AgentTrace`` ready for scoring.
    """
    conv_id = conversation_data.get("id", "unknown")
    domain = conversation_data.get("domain", "unknown")
    messages = conversation_data.get("conversations", [])
    resolved = conversation_data.get("resolved", False)

    turns: list[Turn] = []
    turn_number = 0

    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "")

        if role == "user":
            # User message → decision event (agent receiving input)
            turn_number += 1
            event = TraceEvent(
                event_type="decision",
                data={
                    "action": "user_message",
                    "content": msg.get("content", ""),
                    "domain": domain,
                },
            )
            turns.append(
                Turn(
                    turn_number=turn_number,
                    events=[event],
                    reasoning="user_input",
                )
            )

        elif role == "assistant":
            # Agent reply
            turn_number += 1
            content = msg.get("content", "")
            event = TraceEvent(
                event_type="decision",
                data={
                    "action": "assistant_reply",
                    "content": content,
                    "domain": domain,
                },
            )
            turns.append(
                Turn(
                    turn_number=turn_number,
                    events=[event],
                    reasoning="assistant_reply",
                )
            )

        elif role == "tool_call":
            # Tool call — look ahead for tool_result
            turn_number += 1
            tool_name = msg.get("tool", "unknown")
            tool_args = msg.get("args", {})
            tool_result_str = None
            tool_error = None

            # Look for matching tool_result
            if i + 1 < len(messages) and messages[i + 1].get("role") == "tool_result":
                result_msg = messages[i + 1]
                tool_result_str = str(result_msg.get("result", ""))
                tool_error = result_msg.get("error")
                i += 1  # Skip the tool_result message

            zone_str = (zone_map or {}).get(tool_name)
            security_zone = SecurityZone(zone_str) if zone_str else None

            tool_call = ToolCall(
                tool_name=tool_name,
                arguments=tool_args,
                result=tool_result_str,
                error=tool_error,
            )
            event = TraceEvent(
                event_type="tool_call",
                data={
                    "tool": tool_name,
                    "args": tool_args,
                    "result": tool_result_str,
                    "domain": domain,
                },
                security_zone=security_zone,
            )
            turns.append(
                Turn(
                    turn_number=turn_number,
                    tool_calls=[tool_call],
                    events=[event],
                    reasoning=f"tool_call:{tool_name}",
                )
            )

        elif role == "transfer":
            # Transfer to human → escalation event
            turn_number += 1
            target = msg.get("target", "human_agent")
            event = TraceEvent(
                event_type="escalation",
                data={
                    "action": "transfer_to_human",
                    "target": target,
                    "reason": msg.get("reason", "Agent transferred to human"),
                    "domain": domain,
                },
                escalation_decision=EscalationDecision.ESCALATE,
                escalation_label=EscalationLabel.REQUIRED,
            )
            turns.append(
                Turn(
                    turn_number=turn_number,
                    events=[event],
                    reasoning="escalation:transfer",
                )
            )

        i += 1

    now = datetime.now(UTC).isoformat()
    return AgentTrace(
        adapter_name="tau2bench",
        scenario_name=f"tau2_{domain}_{conv_id}",
        mode=RunMode.REPLAY,
        started_at=now,
        finished_at=now,
        turns=turns,
        success=resolved,
        metadata={
            "source": "tau2bench",
            "domain": domain,
            "conversation_id": conv_id,
            "expected_actions": conversation_data.get("expected_actions", []),
            "expected_outcome": conversation_data.get("expected_outcome", ""),
        },
    )
