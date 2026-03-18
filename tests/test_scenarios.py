"""Tests for Phase 2+3+4 scenarios — base, registry, and concrete scenarios."""

import pytest

from agentbench.adapters.autogen.adapter import AutoGenAdapter
from agentbench.adapters.autogen.scenarios.s1_function_call import S1FunctionCall
from agentbench.adapters.autogen.scenarios.s2_multi_agent_debate import S2MultiAgentDebate
from agentbench.adapters.autogen.scenarios.s3_safety_critical import S3SafetyCritical
from agentbench.adapters.langgraph.adapter import LangGraphAdapter
from agentbench.adapters.langgraph.scenarios.s1_classify_route import S1ClassifyRoute
from agentbench.adapters.langgraph.scenarios.s2_multi_agent import S2MultiAgent
from agentbench.adapters.langgraph.scenarios.s3_error_recovery import S3ErrorRecovery
from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.scenarios.s1_bugfix import S1SoloBugfix
from agentbench.adapters.orchestrator.scenarios.s2_feature import S2MultiFileFeature
from agentbench.adapters.orchestrator.scenarios.s3_crosspod import S3CrossTeamEscalation
from agentbench.adapters.tau2bench.adapter import TAU2BenchAdapter
from agentbench.adapters.tau2bench.scenarios.s1_simple_booking import S1SimpleBooking
from agentbench.adapters.tau2bench.scenarios.s2_multi_step_retry import S2MultiStepRetry
from agentbench.adapters.tau2bench.scenarios.s3_human_escalation import S3HumanEscalation
from agentbench.scenarios.base import VerificationResult, make_config
from agentbench.scenarios.registry import ScenarioRegistry, get_registry, reset_registry
from agentbench.types import AgentTrace, EscalationLabel

# =========================================================================
# BaseScenario + make_config
# =========================================================================


class TestMakeConfig:
    def test_make_config_basic(self) -> None:
        cfg = make_config("test_scenario", description="A test")
        assert cfg.name == "test_scenario"
        assert cfg.description == "A test"
        assert cfg.expected_files == []

    def test_make_config_with_files(self) -> None:
        cfg = make_config("test", expected_files=["a.py", "b.py"])
        assert cfg.expected_files == ["a.py", "b.py"]

    def test_make_config_with_ground_truth(self) -> None:
        gt = {"auth.py": EscalationLabel.REQUIRED}
        cfg = make_config("test", ground_truth=gt)
        assert cfg.ground_truth_labels == gt


class TestVerificationResult:
    def test_passed_true(self) -> None:
        vr = VerificationResult(passed=True, checks={"a": True})
        assert vr.passed is True

    def test_passed_false(self) -> None:
        vr = VerificationResult(passed=False, checks={"a": False}, notes=["oops"])
        assert vr.passed is False
        assert len(vr.notes) == 1


# =========================================================================
# ScenarioRegistry
# =========================================================================


class TestScenarioRegistry:
    def test_register_and_get(self) -> None:
        reg = ScenarioRegistry()
        reg.register("s1", S1SoloBugfix)
        scenario = reg.get("s1")
        assert isinstance(scenario, S1SoloBugfix)

    def test_get_unknown_raises(self) -> None:
        reg = ScenarioRegistry()
        with pytest.raises(KeyError, match="Unknown scenario"):
            reg.get("nonexistent")

    def test_list_scenarios(self) -> None:
        reg = ScenarioRegistry()
        reg.register("b", S1SoloBugfix)
        reg.register("a", S2MultiFileFeature)
        assert reg.list_scenarios() == ["a", "b"]  # sorted

    def test_contains(self) -> None:
        reg = ScenarioRegistry()
        reg.register("x", S1SoloBugfix)
        assert "x" in reg
        assert "y" not in reg

    def test_len(self) -> None:
        reg = ScenarioRegistry()
        assert len(reg) == 0
        reg.register("a", S1SoloBugfix)
        assert len(reg) == 1


class TestAutoDiscovery:
    def test_global_registry_discovers_scenarios(self) -> None:
        registry = get_registry()
        names = registry.list_scenarios()
        assert len(names) >= 12  # 3 orchestrator + 3 langgraph + 3 autogen + 3 tau2bench
        assert "orchestrator_s1_solo_bugfix" in names
        assert "langgraph_s1_classify_route" in names
        assert "langgraph_s2_multi_agent" in names
        assert "langgraph_s3_error_recovery" in names
        assert "autogen_s1_function_call" in names
        assert "autogen_s2_multi_agent_debate" in names
        assert "autogen_s3_safety_critical" in names
        assert "tau2_s1_simple_booking" in names
        assert "tau2_s2_multi_step_retry" in names
        assert "tau2_s3_human_escalation" in names

    def test_reset_registry_clears_state(self) -> None:
        """reset_registry() must clear the singleton so next get_registry() re-discovers."""
        reg1 = get_registry()
        count_before = len(reg1)
        assert count_before >= 12

        reset_registry()

        # After reset, a fresh call must re-discover all scenarios
        reg2 = get_registry()
        assert len(reg2) >= 12
        # Must be a different object (fresh instance)
        assert reg2 is not reg1


# =========================================================================
# Orchestrator Scenarios — Config + Actions
# =========================================================================


class TestOrchestratorS1:
    def test_config(self) -> None:
        s = S1SoloBugfix()
        cfg = s.config
        assert cfg.name == "orchestrator_s1_solo_bugfix"
        assert cfg.adapter_name == "orchestrator"
        assert "app/models/types.py" in cfg.expected_files

    def test_actions_not_empty(self) -> None:
        s = S1SoloBugfix()
        actions = s.get_actions()
        assert len(actions) >= 5

    def test_verify_on_success_trace(self) -> None:
        s = S1SoloBugfix()
        adapter = OrchestratorAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert result.passed
        assert result.checks.get("trace_success") is True

    def test_verify_on_failure_trace(self) -> None:
        s = S1SoloBugfix()
        trace = AgentTrace(success=False, turns=[])
        result = s.verify(trace)
        assert not result.passed


class TestOrchestratorS2:
    def test_config(self) -> None:
        s = S2MultiFileFeature()
        cfg = s.config
        assert "s2" in cfg.name
        assert cfg.adapter_name == "orchestrator"

    def test_actions_include_escalation(self) -> None:
        s = S2MultiFileFeature()
        actions = s.get_actions()
        esc_actions = [a for a in actions if a.action_type == "escalate"]
        assert len(esc_actions) >= 1

    def test_full_execution(self) -> None:
        s = S2MultiFileFeature()
        adapter = OrchestratorAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        # Sensitive scenario should verify escalation correctly
        assert isinstance(result, VerificationResult)


class TestOrchestratorS3:
    def test_config(self) -> None:
        s = S3CrossTeamEscalation()
        cfg = s.config
        assert "s3" in cfg.name

    def test_actions_include_multiple_escalations(self) -> None:
        s = S3CrossTeamEscalation()
        actions = s.get_actions()
        esc_actions = [a for a in actions if a.action_type == "escalate"]
        assert len(esc_actions) >= 2

    def test_full_execution(self) -> None:
        s = S3CrossTeamEscalation()
        adapter = OrchestratorAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)


# =========================================================================
# LangGraph Scenario S1
# =========================================================================


class TestLangGraphS1:
    def test_config(self) -> None:
        s = S1ClassifyRoute()
        cfg = s.config
        assert "langgraph" in cfg.name
        assert cfg.adapter_name == "langgraph"

    def test_actions_have_4_steps(self) -> None:
        s = S1ClassifyRoute()
        actions = s.get_actions()
        assert len(actions) == 4

    def test_full_execution(self) -> None:
        s = S1ClassifyRoute()
        adapter = LangGraphAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True


# =========================================================================
# LangGraph Scenario S2
# =========================================================================


class TestLangGraphS2:
    def test_config(self) -> None:
        s = S2MultiAgent()
        cfg = s.config
        assert cfg.name == "langgraph_s2_multi_agent"
        assert cfg.adapter_name == "langgraph"
        assert "middleware/rate_limiter.py" in cfg.expected_files

    def test_actions_include_escalation(self) -> None:
        s = S2MultiAgent()
        actions = s.get_actions()
        esc = [a for a in actions if a.action_type == "escalate"]
        assert len(esc) >= 1

    def test_actions_have_8_steps(self) -> None:
        s = S2MultiAgent()
        actions = s.get_actions()
        assert len(actions) == 8

    def test_full_execution(self) -> None:
        s = S2MultiAgent()
        adapter = LangGraphAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True
        assert result.checks.get("has_escalation") is True
        assert result.checks.get("sensitive_zone_detected") is True


# =========================================================================
# LangGraph Scenario S3
# =========================================================================


class TestLangGraphS3:
    def test_config(self) -> None:
        s = S3ErrorRecovery()
        cfg = s.config
        assert cfg.name == "langgraph_s3_error_recovery"
        assert cfg.adapter_name == "langgraph"
        assert "auth/routes.py" in cfg.expected_files

    def test_actions_include_dual_escalation(self) -> None:
        s = S3ErrorRecovery()
        actions = s.get_actions()
        esc = [a for a in actions if a.action_type == "escalate"]
        assert len(esc) >= 2

    def test_actions_have_10_steps(self) -> None:
        s = S3ErrorRecovery()
        actions = s.get_actions()
        assert len(actions) == 10

    def test_full_execution(self) -> None:
        s = S3ErrorRecovery()
        adapter = LangGraphAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("has_mandatory_escalation") is True
        assert result.checks.get("critical_zone_detected") is True
        assert result.checks.get("retry_loop") is True


# =========================================================================
# AutoGen Scenario S1
# =========================================================================


class TestAutoGenS1:
    def test_config(self) -> None:
        s = S1FunctionCall()
        cfg = s.config
        assert cfg.name == "autogen_s1_function_call"
        assert cfg.adapter_name == "autogen"
        assert "utils/data_loader.py" in cfg.expected_files

    def test_actions_have_4_steps(self) -> None:
        s = S1FunctionCall()
        actions = s.get_actions()
        assert len(actions) == 4

    def test_full_execution(self) -> None:
        s = S1FunctionCall()
        adapter = AutoGenAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True
        assert result.checks.get("has_function_calls") is True


# =========================================================================
# AutoGen Scenario S2
# =========================================================================


class TestAutoGenS2:
    def test_config(self) -> None:
        s = S2MultiAgentDebate()
        cfg = s.config
        assert cfg.name == "autogen_s2_multi_agent_debate"
        assert cfg.adapter_name == "autogen"
        assert "config/cache_settings.py" in cfg.expected_files

    def test_actions_include_escalation(self) -> None:
        s = S2MultiAgentDebate()
        actions = s.get_actions()
        esc = [a for a in actions if a.action_type == "escalate"]
        assert len(esc) >= 1

    def test_actions_have_8_steps(self) -> None:
        s = S2MultiAgentDebate()
        actions = s.get_actions()
        assert len(actions) == 8

    def test_full_execution(self) -> None:
        s = S2MultiAgentDebate()
        adapter = AutoGenAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True
        assert result.checks.get("has_escalation") is True
        assert result.checks.get("review_retry") is True
        assert result.checks.get("multi_agent") is True


# =========================================================================
# AutoGen Scenario S3
# =========================================================================


class TestAutoGenS3:
    def test_config(self) -> None:
        s = S3SafetyCritical()
        cfg = s.config
        assert cfg.name == "autogen_s3_safety_critical"
        assert cfg.adapter_name == "autogen"
        assert "auth/routes.py" in cfg.expected_files

    def test_actions_include_dual_escalation(self) -> None:
        s = S3SafetyCritical()
        actions = s.get_actions()
        esc = [a for a in actions if a.action_type == "escalate"]
        assert len(esc) >= 2

    def test_actions_have_10_steps(self) -> None:
        s = S3SafetyCritical()
        actions = s.get_actions()
        assert len(actions) == 10

    def test_full_execution(self) -> None:
        s = S3SafetyCritical()
        adapter = AutoGenAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("has_mandatory_escalation") is True
        assert result.checks.get("dual_escalation") is True
        assert result.checks.get("auth_files_edited") is True
        assert result.checks.get("review_fail_then_pass") is True


# =========================================================================
# TAU2-Bench Scenario S1
# =========================================================================


class TestTAU2S1:
    def test_config(self) -> None:
        s = S1SimpleBooking()
        cfg = s.config
        assert cfg.name == "tau2_s1_simple_booking"
        assert cfg.adapter_name == "tau2bench"

    def test_actions_have_5_steps(self) -> None:
        s = S1SimpleBooking()
        actions = s.get_actions()
        assert len(actions) == 5

    def test_full_execution(self) -> None:
        s = S1SimpleBooking()
        adapter = TAU2BenchAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True
        assert result.checks.get("has_tool_call") is True
        assert result.checks.get("no_escalation") is True
        assert result.checks.get("correct_tool") is True


# =========================================================================
# TAU2-Bench Scenario S2
# =========================================================================


class TestTAU2S2:
    def test_config(self) -> None:
        s = S2MultiStepRetry()
        cfg = s.config
        assert cfg.name == "tau2_s2_multi_step_retry"
        assert cfg.adapter_name == "tau2bench"

    def test_actions_have_8_steps(self) -> None:
        s = S2MultiStepRetry()
        actions = s.get_actions()
        assert len(actions) == 8

    def test_full_execution(self) -> None:
        s = S2MultiStepRetry()
        adapter = TAU2BenchAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        trace.success = True
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("trace_success") is True
        assert result.checks.get("multiple_tool_calls") is True
        assert result.checks.get("has_retry") is True
        assert result.checks.get("correct_tools") is True
        assert result.checks.get("no_escalation") is True


# =========================================================================
# TAU2-Bench Scenario S3
# =========================================================================


class TestTAU2S3:
    def test_config(self) -> None:
        s = S3HumanEscalation()
        cfg = s.config
        assert cfg.name == "tau2_s3_human_escalation"
        assert cfg.adapter_name == "tau2bench"

    def test_actions_have_10_steps(self) -> None:
        s = S3HumanEscalation()
        actions = s.get_actions()
        assert len(actions) == 10

    def test_full_execution(self) -> None:
        s = S3HumanEscalation()
        adapter = TAU2BenchAdapter()
        adapter.setup_scenario(s.config)

        for action in s.get_actions():
            adapter.execute_turn(action)

        trace = adapter.get_trace()
        # S3: escalation to human is the key outcome
        result = s.verify(trace)
        assert isinstance(result, VerificationResult)
        assert result.checks.get("has_escalation") is True
        assert result.checks.get("has_tool_calls") is True
        assert result.checks.get("correct_tools") is True
        assert result.checks.get("critical_zone_used") is True
