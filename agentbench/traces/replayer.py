"""Trace replayer — deterministic re-evaluation of recorded traces.

Supports optional policy override: when a policy is provided, escalation
decisions are re-computed from the policy instead of using the pre-recorded
decisions in the trace. This enables meaningful v0/v1/v2 comparison.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbench.config import EvalConfig
from agentbench.instruments.containment import ContainmentTracker
from agentbench.instruments.reliability import ReliabilityTracker
from agentbench.instruments.safety_checker import SafetyChecker
from agentbench.instruments.token_counter import TokenCounter
from agentbench.scoring import ScoringInput, compute_score
from agentbench.traces import load_trace
from agentbench.types import (
    AgentTrace,
    EscalationDecision,
    EscalationLabel,
    EvalResult,
    SecurityZone,
    TurnContext,
    ViolationSeverity,
)

if TYPE_CHECKING:
    from agentbench.policies.escalation import EscalationPolicy
    from agentbench.types import TraceEvent, Turn


def _resolve_enum(value: object, target_val: str) -> bool:
    """Compare an enum or string value against a target string."""
    if value is None:
        return False
    raw = value.value if hasattr(value, "value") else str(value)
    return raw == target_val


def _build_context(event: TraceEvent, turn: Turn) -> TurnContext:
    """Build a TurnContext from a trace event for policy evaluation."""
    zone = event.security_zone or SecurityZone.NORMAL
    if isinstance(zone, str):
        zone = SecurityZone(zone)
    return TurnContext(
        file_path=event.file_path,
        security_zone=zone,
        confidence=event.data.get("confidence", 0.8),
        retry_count=event.data.get("retry_count", 0),
        tokens_used=turn.tokens_input + turn.tokens_output,
        token_budget=event.data.get("token_budget", 50_000),
        turn_number=turn.turn_number,
    )


def _apply_policy_decision(
    event: TraceEvent,
    turn: Turn,
    policy: EscalationPolicy,
) -> EscalationDecision:
    """Apply a policy to an event and return the decision."""
    ctx = _build_context(event, turn)
    return policy.should_escalate(ctx)


def replay_trace(
    trace: AgentTrace,
    *,
    zone_map: dict[str, SecurityZone] | None = None,
    config: EvalConfig | None = None,
    policy: EscalationPolicy | None = None,
) -> EvalResult:
    """Replay a recorded trace and compute evaluation metrics (deterministic, free).

    This is the core of the Trace-Replay mode: no LLM calls, just re-evaluation
    of previously recorded agent decisions against the scoring engine.

    Args:
        trace: The recorded agent trace to replay.
        zone_map: Security zone mapping for safety checking.
        config: Evaluation configuration (weights, thresholds).
        policy: Optional escalation policy to apply. When provided, the policy
            re-computes escalation decisions from trace context instead of using
            pre-recorded decisions. This enables v0/v1/v2 comparison.

    Returns:
        Complete evaluation result with per-dimension scores.
    """
    cfg = config or EvalConfig()

    # Initialize instruments
    safety = SafetyChecker(zone_map=zone_map or {})
    containment = ContainmentTracker()
    reliability = ReliabilityTracker()
    tokens = TokenCounter()

    turn_latencies: list[float] = []
    total_actions = 0
    tasks_succeeded = int(trace.success)
    violations: list[ViolationSeverity] = []
    autonomy_eligible = 0
    autonomy_completed = 0

    for turn in trace.turns:
        turn_latencies.append(turn.duration_ms)
        tokens.add(input_tokens=turn.tokens_input, output_tokens=turn.tokens_output)

        for event in turn.events:
            total_actions += 1

            # Safety
            violation = safety.check_event(event)
            if violation:
                violations.append(violation.severity)

            # Containment — policy override or pre-recorded
            if policy is not None and event.escalation_label is not None:
                # Re-compute the decision using the provided policy
                decision = _apply_policy_decision(event, turn, policy)
                label = event.escalation_label
                if isinstance(label, str):
                    label = EscalationLabel(label)
                containment.record(label, decision)
            else:
                containment.record_from_event(event)

            # Reliability
            reliability.record_from_event(event)

            # Autonomy (only count events with ground-truth labels)
            label = event.escalation_label
            if label is not None:
                if _resolve_enum(label, "autonomous_ok"):
                    autonomy_eligible += 1
                    if policy is not None:
                        esc_decision = _apply_policy_decision(event, turn, policy)
                        if _resolve_enum(esc_decision, "autonomous"):
                            autonomy_completed += 1
                    else:
                        decision = event.escalation_decision
                        if _resolve_enum(decision, "autonomous"):
                            autonomy_completed += 1

    # Build scoring input
    metrics = ScoringInput(
        tasks_attempted=1,
        tasks_succeeded=tasks_succeeded,
        turn_latencies_ms=turn_latencies,
        task_latency_ms=trace.total_duration_ms,
        total_tokens=tokens.total_tokens,
        cost_usd=tokens.cost_usd(),
        violations=violations,
        total_actions=max(total_actions, 1),
        containment=containment.matrix,
        failures=reliability.breakdown,
        autonomy_eligible=autonomy_eligible,
        autonomy_completed=autonomy_completed,
    )

    return compute_score(trace, metrics, cfg)


def replay_trace_file(
    path: Path,
    *,
    zone_map: dict[str, SecurityZone] | None = None,
    config: EvalConfig | None = None,
    policy: EscalationPolicy | None = None,
) -> EvalResult:
    """Load and replay a trace from a JSONL file."""
    trace = load_trace(path)
    return replay_trace(trace, zone_map=zone_map, config=config, policy=policy)


def replay_traces(
    traces: list[AgentTrace],
    *,
    zone_map: dict[str, SecurityZone] | None = None,
    config: EvalConfig | None = None,
    policy: EscalationPolicy | None = None,
) -> list[EvalResult]:
    """Replay multiple traces and return results for each."""
    return [replay_trace(t, zone_map=zone_map, config=config, policy=policy) for t in traces]
