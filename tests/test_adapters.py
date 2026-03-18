"""Tests for Phase 2 adapters — Orchestrator and LangGraph."""

import pytest

from agentbench.adapters.langgraph.adapter import LangGraphAdapter
from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.zones import (
    CRITICAL_PATHS,
    ORCHESTRATOR_ZONE_MAP,
    SENSITIVE_PATHS,
)
from agentbench.types import AgentAction, SecurityZone, TurnContext

# =========================================================================
# Orchestrator Zones
# =========================================================================


class TestOrchestratorZones:
    def test_zone_map_has_all_critical_paths(self) -> None:
        for path in CRITICAL_PATHS:
            assert path in ORCHESTRATOR_ZONE_MAP
            assert ORCHESTRATOR_ZONE_MAP[path] == SecurityZone.CRITICAL

    def test_zone_map_has_all_sensitive_paths(self) -> None:
        for path in SENSITIVE_PATHS:
            assert path in ORCHESTRATOR_ZONE_MAP
            assert ORCHESTRATOR_ZONE_MAP[path] == SecurityZone.SENSITIVE

    def test_get_applicable_principles_policy(self) -> None:
        # Orchestrator zones: policies/ is SENSITIVE
        zone = ORCHESTRATOR_ZONE_MAP.get("policies/")
        assert zone == SecurityZone.SENSITIVE

    def test_get_applicable_principles_normal(self) -> None:
        # Unknown paths default to NORMAL
        zone = ORCHESTRATOR_ZONE_MAP.get("app/core/loop.py", SecurityZone.NORMAL)
        assert zone == SecurityZone.NORMAL


# =========================================================================
# Orchestrator Adapter — Core
# =========================================================================


class TestOrchestratorAdapter:
    @pytest.fixture()
    def adapter(self) -> OrchestratorAdapter:
        return OrchestratorAdapter()

    def test_name(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.name == "orchestrator"

    def test_zone_lookup_critical(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.get_security_zone("auth/routes.py") == SecurityZone.CRITICAL

    def test_zone_lookup_sensitive(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.get_security_zone("policies/rules.py") == SecurityZone.SENSITIVE

    def test_zone_lookup_normal(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.get_security_zone("app/core/loop.py") == SecurityZone.NORMAL

    def test_escalation_needed_critical(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.check_escalation_needed("auth/routes.py") is True

    def test_escalation_needed_normal(self, adapter: OrchestratorAdapter) -> None:
        assert adapter.check_escalation_needed("app/core/loop.py") is False

    def test_escalation_with_context_critical(self, adapter: OrchestratorAdapter) -> None:
        ctx = TurnContext(security_zone=SecurityZone.CRITICAL, confidence=1.0)
        assert adapter.check_escalation_with_context(ctx) is True

    def test_escalation_with_context_sensitive_low_confidence(self, adapter: OrchestratorAdapter) -> None:
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE, confidence=0.5)
        assert adapter.check_escalation_with_context(ctx) is True

    def test_escalation_with_context_sensitive_high_confidence(self, adapter: OrchestratorAdapter) -> None:
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE, confidence=0.9)
        assert adapter.check_escalation_with_context(ctx) is False

    def test_escalation_with_context_retry_limit(self, adapter: OrchestratorAdapter) -> None:
        ctx = TurnContext(security_zone=SecurityZone.NORMAL, retry_count=2)
        assert adapter.check_escalation_with_context(ctx) is True


# =========================================================================
# Orchestrator Adapter — Tool Simulation
# =========================================================================


class TestOrchestratorToolSim:
    @pytest.fixture()
    def adapter(self) -> OrchestratorAdapter:
        a = OrchestratorAdapter()
        a.setup_scenario(None)
        return a

    def test_claim_task(self, adapter: OrchestratorAdapter) -> None:
        action = AgentAction(
            action_type="tool_call",
            tool_name="claim_task",
            arguments={"task_id": "T-001", "orchestrator_id": "eval"},
        )
        result = adapter.execute_turn(action)
        assert result.success

    def test_claim_duplicate_fails(self, adapter: OrchestratorAdapter) -> None:
        action = AgentAction(
            action_type="tool_call",
            tool_name="claim_task",
            arguments={"task_id": "T-001", "orchestrator_id": "eval"},
        )
        adapter.execute_turn(action)
        result2 = adapter.execute_turn(action)
        assert not result2.success

    def test_claim_max_exceeded(self, adapter: OrchestratorAdapter) -> None:
        for i in range(3):
            adapter.execute_turn(
                AgentAction(
                    action_type="tool_call",
                    tool_name="claim_task",
                    arguments={"task_id": f"T-{i:03d}", "orchestrator_id": "eval"},
                )
            )
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="claim_task",
                arguments={"task_id": "T-999", "orchestrator_id": "eval"},
            )
        )
        assert not result.success

    def test_complete_task(self, adapter: OrchestratorAdapter) -> None:
        adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="claim_task",
                arguments={"task_id": "T-001", "orchestrator_id": "eval"},
            )
        )
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="complete_task",
                arguments={"task_id": "T-001"},
            )
        )
        assert result.success

    def test_complete_unclaimed_fails(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="complete_task",
                arguments={"task_id": "T-999"},
            )
        )
        assert not result.success

    def test_release_task(self, adapter: OrchestratorAdapter) -> None:
        adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="claim_task",
                arguments={"task_id": "T-001", "orchestrator_id": "eval"},
            )
        )
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="release_task",
                arguments={"task_id": "T-001"},
            )
        )
        assert result.success

    def test_qc_passes(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="run_quality_check",
                arguments={},
            )
        )
        assert result.success

    def test_auto_assign(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="auto_assign_task",
                arguments={"files": ["auth/routes.py"]},
            )
        )
        assert result.success


# =========================================================================
# Orchestrator Adapter — File Edit + Escalation
# =========================================================================


class TestOrchestratorFileEdit:
    @pytest.fixture()
    def adapter(self) -> OrchestratorAdapter:
        a = OrchestratorAdapter()
        a.setup_scenario(None)
        return a

    def test_normal_file_edit_succeeds(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="file_edit",
                file_path="app/models/types.py",
                arguments={"change": "add enum value"},
            )
        )
        assert result.success

    def test_critical_file_edit_fails(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="file_edit",
                file_path="auth/routes.py",
                arguments={"change": "add endpoint"},
            )
        )
        assert not result.success
        assert result.error is not None
        assert "CRITICAL" in result.error

    def test_escalation_records_event(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="escalate",
                file_path="auth/routes.py",
                arguments={"reason": "Critical zone change"},
            )
        )
        assert result.success
        esc_events = [e for e in result.events if e.event_type == "escalation"]
        assert len(esc_events) == 1

    def test_unknown_action_fails(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="unknown_action",
                arguments={},
            )
        )
        assert not result.success

    def test_complete_action(self, adapter: OrchestratorAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="complete",
                arguments={"reason": "done"},
            )
        )
        assert result.success


# =========================================================================
# Orchestrator Adapter — Trace Recording
# =========================================================================


class TestOrchestratorTraceRecording:
    def test_get_trace_records_all_turns(self) -> None:
        adapter = OrchestratorAdapter()
        adapter.setup_scenario(None)

        adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="claim_task",
                arguments={"task_id": "T-001", "orchestrator_id": "eval"},
            )
        )
        adapter.execute_turn(
            AgentAction(
                action_type="file_edit",
                file_path="app/models/types.py",
                arguments={"change": "fix"},
            )
        )

        trace = adapter.get_trace()
        assert len(trace.turns) == 2
        assert trace.adapter_name == "orchestrator"

    def test_setup_clears_state(self) -> None:
        adapter = OrchestratorAdapter()
        adapter.setup_scenario(None)
        adapter.execute_turn(
            AgentAction(
                action_type="tool_call",
                tool_name="claim_task",
                arguments={"task_id": "T-001", "orchestrator_id": "eval"},
            )
        )
        # Re-setup should clear
        adapter.setup_scenario(None)
        trace = adapter.get_trace()
        assert len(trace.turns) == 0


# =========================================================================
# LangGraph Adapter
# =========================================================================


class TestLangGraphAdapter:
    @pytest.fixture()
    def adapter(self) -> LangGraphAdapter:
        a = LangGraphAdapter()
        a.setup_scenario(None)
        return a

    def test_name(self, adapter: LangGraphAdapter) -> None:
        assert adapter.name == "langgraph"

    def test_classify_node(self, adapter: LangGraphAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="classify",
                arguments={
                    "task_description": "Fix auth bug",
                    "file_paths": ["app/models/types.py"],
                    "team": "platform",
                    "confidence": 0.9,
                },
            )
        )
        assert result.success
        assert len(result.events) >= 1

    def test_classify_detects_critical_zone(self, adapter: LangGraphAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="classify",
                arguments={
                    "file_paths": ["auth/routes.py"],
                    "team": "platform",
                },
            )
        )
        assert result.success
        zone_data = result.events[0].data.get("zone", "")
        assert "Critical" in zone_data or "CRITICAL" in zone_data.upper()

    def test_analyze_node(self, adapter: LangGraphAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="analyze",
                arguments={"scope_analysis": "Minor fix in types.py"},
            )
        )
        assert result.success

    def test_implement_node(self, adapter: LangGraphAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="implement",
                arguments={"file_path": "app/models/types.py", "change": "add enum"},
            )
        )
        assert result.success

    def test_review_node_passes(self, adapter: LangGraphAdapter) -> None:
        # Set up state so lint/tests pass
        adapter._state["lint_passed"] = True
        adapter._state["tests_passed"] = True
        result = adapter.execute_turn(
            AgentAction(
                action_type="review",
                arguments={"lint_passed": True, "tests_passed": True},
            )
        )
        assert result.success

    def test_full_pipeline(self, adapter: LangGraphAdapter) -> None:
        """Run all 4 nodes in sequence: classify → analyze → implement → review."""
        classify = adapter.execute_turn(
            AgentAction(
                action_type="classify",
                arguments={
                    "task_description": "Fix types.py enum",
                    "file_paths": ["app/models/types.py"],
                },
            )
        )
        assert classify.success

        analyze = adapter.execute_turn(
            AgentAction(
                action_type="analyze",
                arguments={"scope_analysis": "Add Status.ENDED"},
            )
        )
        assert analyze.success

        implement = adapter.execute_turn(
            AgentAction(
                action_type="implement",
                arguments={"file_path": "app/models/types.py", "change": "add ENDED"},
            )
        )
        assert implement.success

        review = adapter.execute_turn(
            AgentAction(
                action_type="review",
                arguments={"lint_passed": True, "tests_passed": True},
            )
        )
        assert review.success

        trace = adapter.get_trace()
        assert len(trace.turns) == 4

    def test_escalate_node(self, adapter: LangGraphAdapter) -> None:
        result = adapter.execute_turn(
            AgentAction(
                action_type="escalate",
                arguments={"reason": "Critical zone requires approval"},
            )
        )
        assert result.success
        esc_events = [e for e in result.events if e.event_type == "escalation"]
        assert len(esc_events) == 1

    def test_zone_lookup(self, adapter: LangGraphAdapter) -> None:
        assert adapter.get_security_zone("auth/routes.py") == SecurityZone.CRITICAL
        assert adapter.get_security_zone("policies/rules.py") == SecurityZone.SENSITIVE
        assert adapter.get_security_zone("app/core/loop.py") == SecurityZone.NORMAL
