"""Tests for escalation policies."""

from agentbench.policies.escalation import (
    NullPolicy,
    RuleBasedPolicy,
)
from agentbench.types import EscalationDecision, SecurityZone, TurnContext


class TestNullPolicy:
    def test_never_escalates(self):
        policy = NullPolicy()
        ctx = TurnContext(security_zone=SecurityZone.CRITICAL)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_name(self):
        assert NullPolicy().name == "null-v0"


class TestRuleBasedPolicy:
    def test_critical_zone_escalates(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.CRITICAL)
        result = policy.evaluate(ctx)
        assert result.should_escalate
        assert any("critical" in r.lower() for r in result.reasons)

    def test_sensitive_zone_escalates(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.SENSITIVE)
        result = policy.evaluate(ctx)
        assert result.should_escalate

    def test_normal_zone_continues(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(security_zone=SecurityZone.NORMAL)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_low_confidence_escalates(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(confidence=0.1)
        result = policy.evaluate(ctx)
        assert result.should_escalate
        assert any("confidence" in r.lower() for r in result.reasons)

    def test_high_confidence_continues(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(confidence=0.9)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_excessive_retries_escalate(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(retry_count=5)
        result = policy.evaluate(ctx)
        assert result.should_escalate
        assert any("retry" in r.lower() for r in result.reasons)

    def test_budget_overrun_escalates(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(tokens_used=100_000, token_budget=50_000)
        result = policy.evaluate(ctx)
        assert result.should_escalate
        assert any("token" in r.lower() for r in result.reasons)

    def test_within_budget_continues(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(tokens_used=30_000, token_budget=50_000)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_multiple_reasons(self):
        policy = RuleBasedPolicy()
        ctx = TurnContext(
            security_zone=SecurityZone.CRITICAL,
            confidence=0.1,
            retry_count=10,
        )
        result = policy.evaluate(ctx)
        assert len(result.reasons) >= 3

    def test_custom_thresholds(self):
        policy = RuleBasedPolicy(max_retries=5, min_confidence=0.5)
        # 3 retries under max=5 → no escalation from retries
        ctx = TurnContext(retry_count=3, confidence=0.8)
        assert policy.should_escalate(ctx) == EscalationDecision.AUTONOMOUS

    def test_name(self):
        assert RuleBasedPolicy().name == "rule-based-v1"
