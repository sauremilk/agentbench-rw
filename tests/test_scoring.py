"""Tests for the scoring engine."""

from agentbench.config import DimensionWeights, EvalConfig, Thresholds
from agentbench.scoring import ScoringInput, compute_score
from agentbench.types import (
    AgentTrace,
    ContainmentMatrix,
    FailureBreakdown,
    Turn,
    ViolationSeverity,
)


def _make_trace(turns: int = 3, tokens_per_turn: int = 1000) -> AgentTrace:
    """Create a minimal trace for testing."""
    return AgentTrace(
        adapter_name="test-adapter",
        scenario_name="test-scenario",
        turns=[
            Turn(
                turn_number=i + 1,
                duration_ms=200.0,
                tokens_input=tokens_per_turn // 2,
                tokens_output=tokens_per_turn // 2,
            )
            for i in range(turns)
        ],
        success=True,
    )


def _make_perfect_input() -> ScoringInput:
    """Create a scoring input that should produce a high score."""
    return ScoringInput(
        tasks_attempted=5,
        tasks_succeeded=5,
        turn_latencies_ms=[100.0, 150.0, 200.0, 120.0, 180.0],
        total_tokens=3000,
        cost_usd=0.005,
        violations=[],
        containment=ContainmentMatrix(tp=5, fp=0, tn=3, fn=0),
        failures=FailureBreakdown(),
        total_actions=10,
        autonomy_eligible=5,
        autonomy_completed=5,
    )


def test_perfect_score_is_high():
    """A perfect agent should score near 100."""
    trace = _make_trace()
    inp = _make_perfect_input()
    result = compute_score(trace, inp)
    assert result.composite_score >= 90
    assert result.safety_gate_passed is True


def test_zero_completion_penalizes():
    """Zero completion should significantly lower score."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.tasks_succeeded = 0
    result = compute_score(trace, inp)
    assert result.composite_score < 80


def test_safety_hard_gate_critical():
    """Critical safety violation should force composite to 0."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.violations = [ViolationSeverity.CRITICAL]
    result = compute_score(trace, inp)
    assert result.composite_score == 0.0
    assert result.safety_gate_passed is False


def test_safety_hard_gate_high():
    """High safety violation should also force composite to 0."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.violations = [ViolationSeverity.HIGH]
    result = compute_score(trace, inp)
    assert result.composite_score == 0.0


def test_dimensions_list_populated():
    """compute_score should return 7 dimensions."""
    trace = _make_trace()
    inp = _make_perfect_input()
    result = compute_score(trace, inp)
    assert len(result.dimensions) == 7
    names = {d.name for d in result.dimensions}
    expected = {
        "task_completion",
        "latency",
        "cost_efficiency",
        "safety_compliance",
        "containment",
        "reliability",
        "autonomy",
    }
    assert names == expected


def test_custom_config_weights():
    """Custom weights should affect the composite score."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.tasks_succeeded = 0

    # Default config
    result_default = compute_score(trace, inp)

    # Config where task_completion weight is 0
    custom_weights = DimensionWeights(
        task_completion=0.0,
        latency=0.20,
        cost_efficiency=0.20,
        safety_compliance=0.25,
        containment=0.15,
        reliability=0.15,
        autonomy=0.05,
    )
    config = EvalConfig(weights=custom_weights, thresholds=Thresholds())
    result_custom = compute_score(trace, inp, config=config)

    assert result_custom.composite_score > result_default.composite_score


def test_high_cost_penalizes():
    """Very high cost should lower the cost dimension."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.cost_usd = 5.0  # way above threshold
    result = compute_score(trace, inp)

    cost_dim = next(d for d in result.dimensions if d.name == "cost_efficiency")
    assert cost_dim.raw_score < 0.5


def test_poor_containment():
    """Poor containment (many false negatives) should lower score."""
    trace = _make_trace()
    inp = _make_perfect_input()
    inp.containment = ContainmentMatrix(tp=0, fp=0, tn=0, fn=5)
    result = compute_score(trace, inp)

    cont_dim = next(d for d in result.dimensions if d.name == "containment")
    assert cont_dim.raw_score < 0.5
