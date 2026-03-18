"""AutoGen adapter — evaluates an AutoGen-based multi-agent system.

Agent pattern:
    UserProxy ↔ Assistant(s) via GroupChat / two-party chat.

Each action maps to one message exchange between agents.  The adapter
tracks the conversation log, function calls executed by the assistant,
and security zone compliance.
"""

from __future__ import annotations

import time
from typing import Any

from agentbench.adapters.base import BaseAdapter, build_zone_map
from agentbench.types import (
    AgentAction,
    EscalationDecision,
    SecurityZone,
    ToolCall,
    TraceEvent,
    TurnResult,
)

# ---------------------------------------------------------------------------
# Zone map (generic, same zones as other adapters)
# ---------------------------------------------------------------------------

_CRITICAL_PATHS = [
    "auth/",
    "auth.py",
    "migrations/",
    ".env",
    "secrets/",
    "db/migrations/",
    "models/user.py",
]

_SENSITIVE_PATHS = [
    "policies/",
    "config/",
    "middleware/",
    "integrations/",
]


class AutoGenAdapter(BaseAdapter):
    """TargetAdapter for evaluating an AutoGen-based multi-agent system.

    Simulates the GroupChat / two-party pattern where a UserProxyAgent
    delegates tasks to one or more AssistantAgents.  Each action
    represents one message exchange in the conversation.

    Supported action types:
    - ``send``      — UserProxy sends a task/message to an agent
    - ``function``  — Assistant calls a registered function (tool)
    - ``reply``     — Assistant sends a text reply
    - ``escalate``  — Agent requests human approval / escalation
    - ``review``    — GroupChat manager triggers a review round
    """

    _zone_map = build_zone_map(critical=_CRITICAL_PATHS, sensitive=_SENSITIVE_PATHS)

    # Action types this adapter understands
    ACTION_TYPES = ("send", "function", "reply", "escalate", "review")

    def __init__(self, *, simulate: bool = True, max_rounds: int = 20) -> None:
        super().__init__()
        self._simulate = simulate
        self._max_rounds = max_rounds

        # Simulated conversation state
        self._messages: list[dict[str, Any]] = []
        self._agents: dict[str, str] = {}  # name → role
        self._function_map: dict[str, str] = {}  # func_name → description
        self._escalated_files: set[str] = set()
        self._round: int = 0

    @property
    def name(self) -> str:
        return "autogen"

    def setup_scenario(self, scenario: Any) -> None:
        super().setup_scenario(scenario)
        self._messages.clear()
        self._agents.clear()
        self._function_map.clear()
        self._escalated_files.clear()
        self._round = 0

        # Inject scenario data
        if self._scenario and self._scenario.inject_data:
            inject = self._scenario.inject_data
            for agent_def in inject.get("agents", []):
                self._agents[agent_def["name"]] = agent_def.get("role", "assistant")
            for fn in inject.get("functions", []):
                self._function_map[fn["name"]] = fn.get("description", "")

    # -----------------------------------------------------------------------
    # Core execution — each action = one message exchange
    # -----------------------------------------------------------------------

    def _do_execute(self, action: AgentAction) -> TurnResult:
        t0 = time.perf_counter()

        handler = self._ACTION_HANDLERS.get(action.action_type, self._handle_unknown)
        result = handler(self, action)

        elapsed = (time.perf_counter() - t0) * 1000
        result.duration_ms = elapsed
        self._round += 1
        return result

    # -----------------------------------------------------------------------
    # Action handlers
    # -----------------------------------------------------------------------

    def _handle_send(self, action: AgentAction) -> TurnResult:
        """UserProxy sends a task or message to an agent."""
        sender = action.arguments.get("sender", "user_proxy")
        receiver = action.arguments.get("receiver", "assistant")
        content = action.arguments.get("content", "")

        self._messages.append(
            {
                "sender": sender,
                "receiver": receiver,
                "content": content,
                "round": self._round,
            }
        )

        event = TraceEvent(
            event_type="decision",
            data={"action": "send", "sender": sender, "receiver": receiver, "round": self._round},
        )
        return TurnResult(success=True, events=[event])

    def _handle_function(self, action: AgentAction) -> TurnResult:
        """Assistant invokes a registered function (tool call)."""
        func_name = action.arguments.get("function_name", "unknown")
        func_args = action.arguments.get("function_args", {})
        result_value = action.arguments.get("result", "ok")
        error = action.arguments.get("error")
        file_path = action.arguments.get("file_path", action.file_path or "")

        success = error is None

        self._messages.append(
            {
                "sender": action.arguments.get("agent", "assistant"),
                "function": func_name,
                "args": func_args,
                "result": result_value,
                "round": self._round,
            }
        )

        zone = self.get_security_zone(file_path) if file_path else SecurityZone.NORMAL

        # Containment tracking
        label = None
        escalation_decision = None
        if self._scenario and self._scenario.ground_truth_labels and file_path:
            label = self._scenario.ground_truth_labels.get(file_path)
            if file_path in self._escalated_files:
                label = None  # Already tracked via escalation
            elif label is not None:
                escalation_decision = EscalationDecision.AUTONOMOUS

        events = [
            TraceEvent(
                event_type="tool_call" if not file_path else "file_edit",
                data={
                    "function": func_name,
                    "args": func_args,
                    "result": result_value,
                    "agent": action.arguments.get("agent", "assistant"),
                },
                file_path=file_path or None,
                security_zone=zone,
                escalation_label=label,
                escalation_decision=escalation_decision,
            ),
        ]

        tool_calls = [
            ToolCall(
                tool_name=func_name,
                arguments=func_args,
                result=str(result_value),
                error=error,
            ),
        ]

        return TurnResult(success=success, events=events, tool_calls=tool_calls, error=error)

    def _handle_reply(self, action: AgentAction) -> TurnResult:
        """Assistant sends a text reply in the conversation."""
        agent = action.arguments.get("agent", "assistant")
        content = action.arguments.get("content", "")
        verdict = action.arguments.get("verdict")  # optional: approve/reject

        self._messages.append(
            {
                "sender": agent,
                "content": content,
                "verdict": verdict,
                "round": self._round,
            }
        )

        event = TraceEvent(
            event_type="decision",
            data={"action": "reply", "agent": agent, "verdict": verdict, "round": self._round},
        )
        return TurnResult(success=True, events=[event])

    def _handle_escalate(self, action: AgentAction) -> TurnResult:
        """Agent requests escalation / human approval."""
        reason = action.arguments.get("reason", "escalation requested")
        zone_str = self._detect_zone_label()
        zone = self._parse_zone(zone_str)

        # Track escalated files
        for fp in self._get_active_files():
            self._escalated_files.add(fp)

        # Ground-truth label
        label = None
        if self._scenario and self._scenario.ground_truth_labels:
            for fp in self._get_active_files():
                label = self._scenario.ground_truth_labels.get(fp)
                if label:
                    break

        event = TraceEvent(
            event_type="escalation",
            data={"reason": reason, "zone": zone_str, "round": self._round},
            security_zone=zone,
            escalation_decision=EscalationDecision.ESCALATE,
            escalation_label=label,
        )

        self._messages.append(
            {
                "sender": action.arguments.get("agent", "assistant"),
                "escalation": reason,
                "round": self._round,
            }
        )

        return TurnResult(success=True, events=[event])

    def _handle_review(self, action: AgentAction) -> TurnResult:
        """GroupChat manager triggers a review round."""
        reviewer = action.arguments.get("reviewer", "reviewer")
        verdict = action.arguments.get("verdict", "approve")
        feedback = action.arguments.get("feedback", "")
        tests_passed = action.arguments.get("tests_passed", True)

        self._messages.append(
            {
                "sender": reviewer,
                "verdict": verdict,
                "feedback": feedback,
                "round": self._round,
            }
        )

        events = [
            TraceEvent(
                event_type="decision",
                data={
                    "action": "review",
                    "reviewer": reviewer,
                    "verdict": verdict,
                    "tests_passed": tests_passed,
                    "round": self._round,
                },
            ),
        ]

        tool_calls = [
            ToolCall(
                tool_name="pytest",
                result="passed" if tests_passed else "failed",
                error=None if tests_passed else feedback,
            ),
        ]

        return TurnResult(
            success=verdict == "approve" and tests_passed,
            events=events,
            tool_calls=tool_calls,
        )

    def _handle_unknown(self, action: AgentAction) -> TurnResult:
        """Fallback for unrecognized action types."""
        event = TraceEvent(
            event_type="decision",
            data={"action": action.action_type, "args": action.arguments},
        )
        return TurnResult(success=True, events=[event])

    _ACTION_HANDLERS: dict[str, Any] = {
        "send": _handle_send,
        "function": _handle_function,
        "reply": _handle_reply,
        "escalate": _handle_escalate,
        "review": _handle_review,
    }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_active_files(self) -> list[str]:
        """Return file paths from the scenario inject data."""
        if self._scenario and self._scenario.inject_data:
            return self._scenario.inject_data.get("file_paths", [])
        return []

    def _detect_zone_label(self) -> str:
        """Detect the highest zone from active files."""
        zone = SecurityZone.NORMAL
        for fp in self._get_active_files():
            z = self.get_security_zone(fp)
            if z == SecurityZone.CRITICAL:
                return "🔴 Critical"
            if z == SecurityZone.SENSITIVE:
                zone = SecurityZone.SENSITIVE
        if zone == SecurityZone.SENSITIVE:
            return "🟡 Sensitive"
        return "🟢 Normal"

    @staticmethod
    def _parse_zone(zone_str: str) -> SecurityZone:
        if "🔴" in zone_str or "critical" in zone_str.lower():
            return SecurityZone.CRITICAL
        if "🟡" in zone_str or "sensitive" in zone_str.lower():
            return SecurityZone.SENSITIVE
        return SecurityZone.NORMAL

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Conversation log."""
        return list(self._messages)

    @property
    def round_count(self) -> int:
        return self._round
