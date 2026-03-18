"""LangGraph adapter — evaluates a LangGraph-based agent workflow.

Graph structure:
    classify → escalate | analyze → implement → review → (END | implement)

Each node transition is recorded as one turn. Node outputs populate
AgentState fields which are captured in trace events.
"""

from __future__ import annotations

import time
from typing import Any

from agentbench.adapters.base import BaseAdapter, build_zone_map
from agentbench.types import (
    AgentAction,
    EscalationDecision,
    EscalationLabel,
    SecurityZone,
    ToolCall,
    TraceEvent,
    TurnResult,
)

# ---------------------------------------------------------------------------
# Zone map for LangGraph (generic security zones)
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


class LangGraphAdapter(BaseAdapter):
    """TargetAdapter for evaluating a LangGraph-based agent workflow.

    Simulates the 5-node graph: classify → escalate | analyze → implement → review.
    Each action maps to a node execution, recording state transitions.

    In live mode, this would invoke the LangGraph workflow.
    In eval/simulate mode, it processes a sequence of node executions
    deterministically against a mocked AgentState.
    """

    _zone_map = build_zone_map(critical=_CRITICAL_PATHS, sensitive=_SENSITIVE_PATHS)

    # The 5 graph nodes in execution order
    GRAPH_NODES = ("classify", "escalate", "analyze", "implement", "review")

    def __init__(self, *, simulate: bool = True, max_retries: int = 3) -> None:
        super().__init__()
        self._simulate = simulate
        self._max_retries = max_retries

        # Simulated AgentState (mirrors agents/langgraph/state.py)
        self._state: dict[str, Any] = {}
        self._node_log: list[dict[str, Any]] = []
        self._escalated_files: set[str] = set()

    @property
    def name(self) -> str:
        return "langgraph"

    def setup_scenario(self, scenario: Any) -> None:
        super().setup_scenario(scenario)
        self._state = {
            "task_description": "",
            "file_paths": [],
            "assigned_pod": "",
            "assigned_agent": "",
            "security_zone": "🟢 Normal",
            "classification_confidence": 0.0,
            "scope_analysis": "",
            "affected_files": [],
            "test_files": [],
            "estimated_complexity": "moderate",
            "changes_made": [],
            "lint_passed": False,
            "lint_output": "",
            "review_passed": False,
            "review_feedback": "",
            "tests_passed": False,
            "test_output": "",
            "iteration": 0,
            "max_retries": self._max_retries,
            "error": "",
            "status": "pending",
        }
        self._node_log.clear()
        self._escalated_files.clear()

        # Inject scenario data into state
        if self._scenario:
            inject = self._scenario.inject_data
            if inject:
                self._state.update(inject)

    # -----------------------------------------------------------------------
    # Core execution — each action = one node transition
    # -----------------------------------------------------------------------

    def _do_execute(self, action: AgentAction) -> TurnResult:
        t0 = time.perf_counter()

        node_name = action.arguments.get("node", action.action_type)
        handler = self._NODE_HANDLERS.get(node_name, self._handle_generic_node)
        result = handler(self, action)

        elapsed = (time.perf_counter() - t0) * 1000
        result.duration_ms = elapsed

        self._node_log.append({"node": node_name, "state_snapshot": dict(self._state)})
        return result

    # -----------------------------------------------------------------------
    # Node handlers
    # -----------------------------------------------------------------------

    def _handle_classify(self, action: AgentAction) -> TurnResult:
        """Simulate the classify node: pod routing + security zone detection."""
        task_desc = action.arguments.get("task_description", self._state.get("task_description", ""))
        file_paths = action.arguments.get("file_paths", self._state.get("file_paths", []))

        self._state["task_description"] = task_desc
        self._state["file_paths"] = file_paths

        # Determine security zone from file paths
        zone = SecurityZone.NORMAL
        zone_label = "🟢 Normal"
        for fp in file_paths:
            z = self.get_security_zone(fp)
            if z == SecurityZone.CRITICAL:
                zone = SecurityZone.CRITICAL
                zone_label = "🔴 Critical"
                break
            if z == SecurityZone.SENSITIVE:
                zone = SecurityZone.SENSITIVE
                zone_label = "🟡 Sensitive"

        self._state["assigned_pod"] = action.arguments.get("pod", "platform")
        self._state["security_zone"] = zone_label
        self._state["classification_confidence"] = action.arguments.get("confidence", 0.85)
        self._state["status"] = "in_progress"

        event = TraceEvent(
            event_type="decision",
            data={
                "node": "classify",
                "pod": self._state["assigned_pod"],
                "zone": zone_label,
                "confidence": self._state["classification_confidence"],
            },
            security_zone=zone,
        )

        tool_call = ToolCall(
            tool_name="classify_node",
            arguments={"task": task_desc, "files": file_paths},
            result=f"pod={self._state['assigned_pod']}, zone={zone_label}",
        )

        return TurnResult(success=True, events=[event], tool_calls=[tool_call])

    def _handle_escalate(self, action: AgentAction) -> TurnResult:
        """Simulate the escalate node: create approval issue, set status=escalated."""
        reason = action.arguments.get("reason", "CRITICAL zone detected")
        self._state["status"] = "escalated"
        self._state["error"] = f"Escalated: {reason}"

        zone = self._parse_zone(self._state.get("security_zone", ""))

        # Track escalated file paths
        for fp in self._state.get("file_paths", []):
            self._escalated_files.add(fp)

        event = TraceEvent(
            event_type="escalation",
            data={"node": "escalate", "reason": reason, "zone": self._state["security_zone"]},
            security_zone=zone,
            escalation_decision=EscalationDecision.ESCALATE,
        )

        # Check ground truth and set confidence
        if self._scenario and self._scenario.ground_truth_labels:
            for fp in self._state.get("file_paths", []):
                label = self._scenario.ground_truth_labels.get(fp)
                if label:
                    event.escalation_label = label
                    event.file_path = fp
                    event.data["confidence"] = self._estimate_confidence(zone, label)
                    break

        return TurnResult(success=True, events=[event])

    def _handle_analyze(self, action: AgentAction) -> TurnResult:
        """Simulate the analyze node: scope analysis, affected files."""
        self._state["scope_analysis"] = action.arguments.get("scope", "analyzed")
        self._state["affected_files"] = action.arguments.get("affected_files", self._state.get("file_paths", []))
        self._state["test_files"] = action.arguments.get("test_files", [])
        self._state["estimated_complexity"] = action.arguments.get("complexity", "moderate")

        event = TraceEvent(
            event_type="decision",
            data={
                "node": "analyze",
                "complexity": self._state["estimated_complexity"],
                "affected": len(self._state["affected_files"]),
            },
        )
        return TurnResult(success=True, events=[event])

    def _estimate_confidence(self, zone: SecurityZone, label: EscalationLabel | None) -> float:
        """Estimate agent confidence based on zone and ground truth."""
        if zone == SecurityZone.CRITICAL:
            return 0.2
        if zone == SecurityZone.SENSITIVE:
            if label == EscalationLabel.REQUIRED:
                return 0.35
            return 0.85
        return 0.9

    def _handle_implement(self, action: AgentAction) -> TurnResult:
        """Simulate the implement node: code changes + lint."""
        changes = action.arguments.get("changes", [])
        lint_passed = action.arguments.get("lint_passed", True)

        self._state["changes_made"].extend(changes)
        self._state["lint_passed"] = lint_passed
        self._state["lint_output"] = action.arguments.get("lint_output", "")
        self._state["iteration"] = self._state.get("iteration", 0) + 1

        events: list[TraceEvent] = []
        tool_calls: list[ToolCall] = []

        for change in changes:
            fp = change.get("file", "")
            zone = self.get_security_zone(fp)

            # Determine ground-truth label for containment tracking
            label = None
            escalation_decision = None
            confidence = self._estimate_confidence(zone, None)
            if self._scenario and self._scenario.ground_truth_labels:
                label = self._scenario.ground_truth_labels.get(fp)
                confidence = self._estimate_confidence(zone, label)

            # Skip containment data if file was already escalated
            if fp in self._escalated_files:
                label = None
            elif label is not None:
                escalation_decision = EscalationDecision.AUTONOMOUS

            events.append(
                TraceEvent(
                    event_type="file_edit",
                    data={"node": "implement", "file": fp, "change": change, "confidence": confidence},
                    file_path=fp,
                    security_zone=zone,
                    escalation_label=label,
                    escalation_decision=escalation_decision,
                )
            )

        if lint_passed:
            tool_calls.append(ToolCall(tool_name="ruff_check", result="passed"))
        else:
            tool_calls.append(ToolCall(tool_name="ruff_check", result="failed", error=self._state["lint_output"]))

        return TurnResult(success=lint_passed, events=events, tool_calls=tool_calls)

    def _handle_review(self, action: AgentAction) -> TurnResult:
        """Simulate the review node: tests + review verdict."""
        review_passed = action.arguments.get("review_passed", True)
        tests_passed = action.arguments.get("tests_passed", True)

        self._state["review_passed"] = review_passed
        self._state["tests_passed"] = tests_passed
        self._state["review_feedback"] = action.arguments.get("feedback", "")
        self._state["test_output"] = action.arguments.get("test_output", "")

        if review_passed and tests_passed:
            self._state["status"] = "done"
        elif self._state.get("iteration", 0) >= self._max_retries:
            self._state["status"] = "failed"
            self._state["error"] = "Max retries exceeded"

        events = [
            TraceEvent(
                event_type="decision",
                data={
                    "node": "review",
                    "review_passed": review_passed,
                    "tests_passed": tests_passed,
                    "iteration": self._state.get("iteration", 0),
                    "status": self._state["status"],
                },
            )
        ]

        tool_calls = [
            ToolCall(
                tool_name="pytest",
                result="passed" if tests_passed else "failed",
                error=None if tests_passed else self._state.get("test_output", ""),
            )
        ]

        return TurnResult(success=review_passed and tests_passed, events=events, tool_calls=tool_calls)

    def _handle_generic_node(self, action: AgentAction) -> TurnResult:
        """Fallback for unknown node names."""
        event = TraceEvent(
            event_type="decision",
            data={"node": action.action_type, "args": action.arguments},
        )
        return TurnResult(success=True, events=[event])

    _NODE_HANDLERS: dict[str, Any] = {
        "classify": _handle_classify,
        "escalate": _handle_escalate,
        "analyze": _handle_analyze,
        "implement": _handle_implement,
        "review": _handle_review,
    }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_zone(zone_str: str) -> SecurityZone:
        """Parse zone label string to SecurityZone enum."""
        if "🔴" in zone_str or "Critical" in zone_str or "critical" in zone_str.lower():
            return SecurityZone.CRITICAL
        if "🟡" in zone_str or "Sensitive" in zone_str or "sensitive" in zone_str.lower():
            return SecurityZone.SENSITIVE
        return SecurityZone.NORMAL

    @property
    def state(self) -> dict[str, Any]:
        """Current AgentState snapshot."""
        return dict(self._state)

    @property
    def node_log(self) -> list[dict[str, Any]]:
        """Log of node executions with state snapshots."""
        return list(self._node_log)
