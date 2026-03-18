"""Escalation policies — when should an agent ask for human help?

v0: NullPolicy — never escalates (baseline).
v1: RuleBasedPolicy — rule-based escalation from predefined security zones.
v2: TunedPolicy — thresholds optimized via grid-search on recorded traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from agentbench.types import EscalationDecision, SecurityZone, TurnContext


class EscalationPolicy(Protocol):
    """Protocol for escalation decision logic."""

    @property
    def name(self) -> str: ...

    def should_escalate(self, context: TurnContext) -> EscalationDecision: ...


@dataclass
class EscalationResult:
    """Detailed result of an escalation check."""

    decision: EscalationDecision
    reasons: list[str] = field(default_factory=list)

    @property
    def should_escalate(self) -> bool:
        return self.decision == EscalationDecision.ESCALATE


# ---------------------------------------------------------------------------
# v0: NullPolicy — Baseline (never escalates)
# ---------------------------------------------------------------------------


class NullPolicy:
    """Never escalates. Baseline for measuring escalation delta."""

    @property
    def name(self) -> str:
        return "null-v0"

    def should_escalate(self, context: TurnContext) -> EscalationDecision:
        return EscalationDecision.AUTONOMOUS


# ---------------------------------------------------------------------------
# v1: RuleBasedPolicy — deterministic rules from security zone definitions
# ---------------------------------------------------------------------------

# Default thresholds — can be overridden at construction time
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_BUDGET_MULTIPLIER = 1.5
_DEFAULT_MIN_CONFIDENCE = 0.3


@dataclass
class RuleBasedPolicy:
    """Rule-based escalation based on security zone classifications.

    Rules:
    1. SecurityZone.CRITICAL → always ESCALATE
    2. SecurityZone.SENSITIVE → ESCALATE
    3. Confidence < min_confidence → ESCALATE
    4. Retry count > max_retries → ESCALATE
    5. Token budget > budget_multiplier × expected → ESCALATE
    """

    max_retries: int = _DEFAULT_MAX_RETRIES
    budget_multiplier: float = _DEFAULT_BUDGET_MULTIPLIER
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE

    @property
    def name(self) -> str:
        return "rule-based-v1"

    def should_escalate(self, context: TurnContext) -> EscalationDecision:
        return self.evaluate(context).decision

    def evaluate(self, context: TurnContext) -> EscalationResult:
        """Evaluate with detailed reasoning."""
        reasons: list[str] = []

        # Rule 1+2: Security zone
        if context.security_zone == SecurityZone.CRITICAL:
            reasons.append(f"Zone {context.security_zone}: critical files require user approval")
        elif context.security_zone == SecurityZone.SENSITIVE:
            reasons.append(f"Zone {context.security_zone}: sensitive files need peer review")

        # Rule 3: Low confidence
        if context.confidence < self.min_confidence:
            reasons.append(f"Confidence {context.confidence:.2f} below threshold {self.min_confidence}")

        # Rule 4: Excessive retries
        if context.retry_count > self.max_retries:
            reasons.append(f"Retry count {context.retry_count} exceeds max {self.max_retries}")

        # Rule 5: Budget overrun
        if context.token_budget > 0 and context.tokens_used > self.budget_multiplier * context.token_budget:
            reasons.append(
                f"Token usage {context.tokens_used} exceeds {self.budget_multiplier}x budget ({context.token_budget})"
            )

        if reasons:
            return EscalationResult(
                decision=EscalationDecision.ESCALATE,
                reasons=reasons,
            )
        return EscalationResult(decision=EscalationDecision.AUTONOMOUS)


# ---------------------------------------------------------------------------
# v2: TunedPolicy — thresholds optimized via grid-search on traces
# ---------------------------------------------------------------------------

# Optimized defaults (derived from grid-search over S1-S3 baseline traces)
_TUNED_MAX_RETRIES = 2
_TUNED_BUDGET_MULTIPLIER = 1.2  # tighter than v1's 1.5 — catches budget overruns earlier
_TUNED_MIN_CONFIDENCE = 0.45  # higher than v1's 0.3 — fewer false negatives


@dataclass
class TunedPolicy:
    """Escalation policy with thresholds optimized via trace replay.

    Key changes from v1 (RuleBasedPolicy):
    - confidence_threshold: 0.3 → 0.45 (FN-analysis: low-confidence turns often needed escalation)
    - budget_multiplier: 1.5 → 1.2 (cost-analysis: 1.5x too generous, missed over-budget turns)
    - SENSITIVE zone: escalate only if confidence < threshold (FP-analysis: not all SENSITIVE actions
      need escalation — only uncertain ones do)
    """

    max_retries: int = _TUNED_MAX_RETRIES
    budget_multiplier: float = _TUNED_BUDGET_MULTIPLIER
    min_confidence: float = _TUNED_MIN_CONFIDENCE

    @property
    def name(self) -> str:
        return "tuned-v2"

    def should_escalate(self, context: TurnContext) -> EscalationDecision:
        return self.evaluate(context).decision

    def evaluate(self, context: TurnContext) -> EscalationResult:
        """Evaluate with detailed reasoning."""
        reasons: list[str] = []

        # Rule 1: CRITICAL zone always escalates (unchanged from v1)
        if context.security_zone == SecurityZone.CRITICAL:
            reasons.append(f"Zone {context.security_zone}: critical files require user approval")

        # Rule 2: SENSITIVE zone — only escalate when confidence is low (tuned from v1)
        elif context.security_zone == SecurityZone.SENSITIVE and context.confidence < self.min_confidence:
            reasons.append(
                f"Zone {context.security_zone} with low confidence {context.confidence:.2f} "
                f"(threshold {self.min_confidence})"
            )

        # Rule 3: Low confidence (tighter threshold)
        if context.confidence < self.min_confidence and context.security_zone == SecurityZone.NORMAL:
            reasons.append(f"Confidence {context.confidence:.2f} below tuned threshold {self.min_confidence}")

        # Rule 4: Excessive retries (unchanged)
        if context.retry_count > self.max_retries:
            reasons.append(f"Retry count {context.retry_count} exceeds max {self.max_retries}")

        # Rule 5: Budget overrun (tighter multiplier)
        if context.token_budget > 0 and context.tokens_used > self.budget_multiplier * context.token_budget:
            reasons.append(
                f"Token usage {context.tokens_used} exceeds {self.budget_multiplier}x budget ({context.token_budget})"
            )

        if reasons:
            return EscalationResult(
                decision=EscalationDecision.ESCALATE,
                reasons=reasons,
            )
        return EscalationResult(decision=EscalationDecision.AUTONOMOUS)
