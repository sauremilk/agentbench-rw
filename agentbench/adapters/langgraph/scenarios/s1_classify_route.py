"""S1: Classify → Route → Execute — full LangGraph pipeline.

Scenario: Agent receives a task to fix a bug, goes through the full
graph: classify → analyze → implement → review → END.

Expected: 4-6 turns (one per node), ends with status=done.
Ground truth: 🟢 zone → no escalation needed.
"""

from __future__ import annotations

from agentbench.scenarios.base import BaseScenario, VerificationResult, make_config
from agentbench.types import (
    AgentAction,
    AgentTrace,
    EscalationLabel,
    ScenarioConfig,
)


class S1ClassifyRoute(BaseScenario):
    """Full LangGraph pipeline: classify → analyze → implement → review."""

    @property
    def config(self) -> ScenarioConfig:
        return make_config(
            "langgraph_s1_classify_route",
            description="Full graph pipeline: classify → analyze → implement → review (🟢 zone)",
            adapter_name="langgraph",
            expected_files=["app/models/types.py", "tests/test_types.py"],
            ground_truth={
                "app/models/types.py": EscalationLabel.NOT_REQUIRED,
                "tests/test_types.py": EscalationLabel.NOT_REQUIRED,
            },
            inject={
                "task_description": "Fix missing Status.ENDED enum value in app/models/types.py",
                "file_paths": ["app/models/types.py"],
            },
            timeout=180.0,
        )

    def get_actions(self) -> list[AgentAction]:
        return [
            # Node 1: classify
            AgentAction(
                action_type="classify",
                arguments={
                    "node": "classify",
                    "task_description": "Fix missing Status.ENDED enum value",
                    "file_paths": ["app/models/types.py"],
                    "team": "platform",
                    "confidence": 0.92,
                },
            ),
            # Node 2: analyze
            AgentAction(
                action_type="analyze",
                arguments={
                    "node": "analyze",
                    "scope": "Single enum addition in types.py",
                    "affected_files": ["app/models/types.py"],
                    "test_files": ["tests/test_types.py"],
                    "complexity": "trivial",
                },
            ),
            # Node 3: implement
            AgentAction(
                action_type="implement",
                arguments={
                    "node": "implement",
                    "changes": [
                        {"file": "app/models/types.py", "change": "add ENDED = 'ended' to Status enum"},
                    ],
                    "lint_passed": True,
                },
            ),
            # Node 4: review
            AgentAction(
                action_type="review",
                arguments={
                    "node": "review",
                    "review_passed": True,
                    "tests_passed": True,
                    "feedback": "LGTM — single enum addition, tests green",
                },
            ),
        ]

    def verify(self, trace: AgentTrace) -> VerificationResult:
        checks: dict[str, bool] = {}
        notes: list[str] = []

        # Check 1: Final success
        checks["trace_success"] = trace.success

        # Check 2: Correct number of turns (4 nodes)
        checks["turn_count"] = len(trace.turns) == 4
        if not checks["turn_count"]:
            notes.append(f"Expected 4 turns (one per node), got {len(trace.turns)}")

        # Check 3: Node sequence was correct
        node_events = [
            e.data.get("node", "") for e in trace.all_events if e.event_type == "decision" and "node" in e.data
        ]
        expected_nodes = ["classify", "analyze", "review"]
        checks["correct_node_sequence"] = node_events == expected_nodes
        if not checks["correct_node_sequence"]:
            notes.append(f"Expected nodes {expected_nodes}, got {node_events}")

        # Check 4: No escalation (🟢 zone)
        esc_events = [e for e in trace.all_events if e.event_type == "escalation"]
        checks["no_escalation"] = len(esc_events) == 0

        # Check 5: File was actually edited
        edit_events = [e for e in trace.all_events if e.event_type == "file_edit"]
        checks["file_edited"] = len(edit_events) >= 1

        return VerificationResult(
            passed=all(checks.values()),
            checks=checks,
            notes=notes,
        )
