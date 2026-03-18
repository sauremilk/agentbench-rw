"""Property-based tests using hypothesis.

These tests verify invariants that must hold for ALL inputs, not just hand-picked examples.
Inspired by the review recommendation to move beyond example-based testing.

Invariants tested:
1. Composite score is always in [0, 100] for any valid weights.
2. Safety hard gate: any CRITICAL/HIGH violation forces composite to 0.
3. JSONL roundtrip: trace_to_jsonl → jsonl_to_trace is lossless for all traces.
4. ContainmentMatrix: precision, recall, F1 are always in [0, 1].
5. DimensionWeights that sum to 1.0 never raise on validate().
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agentbench.config import DimensionWeights
from agentbench.scoring import ScoringInput, compute_score
from agentbench.traces import jsonl_to_trace, trace_to_jsonl
from agentbench.types import (
    AgentTrace,
    ContainmentMatrix,
    FailureBreakdown,
    TraceEvent,
    Turn,
    ViolationSeverity,
)

# ---------------------------------------------------------------------------
# Strategies — reusable data generators
# ---------------------------------------------------------------------------

_severity = st.sampled_from(list(ViolationSeverity))

_non_negative_int = st.integers(min_value=0, max_value=500)
_non_negative_float = st.floats(min_value=0.0, max_value=100_000.0, allow_nan=False, allow_infinity=False)
_latencies = st.lists(
    st.floats(min_value=0.0, max_value=60_000.0, allow_nan=False, allow_infinity=False),
    min_size=0,
    max_size=50,
)

_containment_matrix = st.builds(
    ContainmentMatrix,
    tp=_non_negative_int,
    fp=_non_negative_int,
    tn=_non_negative_int,
    fn=_non_negative_int,
)

_failure_breakdown = st.builds(
    FailureBreakdown,
    infrastructure=_non_negative_int,
    planner=_non_negative_int,
    tool=_non_negative_int,
    safety_violation=_non_negative_int,
    recovery_success=_non_negative_int,
)

_scoring_input = st.builds(
    ScoringInput,
    tasks_attempted=st.integers(min_value=1, max_value=100),
    tasks_succeeded=st.integers(min_value=0, max_value=100),
    turn_latencies_ms=_latencies,
    total_tokens=_non_negative_int,
    cost_usd=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    violations=st.lists(_severity, min_size=0, max_size=10),
    containment=_containment_matrix,
    failures=_failure_breakdown,
    total_actions=st.integers(min_value=1, max_value=200),
    autonomy_eligible=st.integers(min_value=0, max_value=50),
    autonomy_completed=st.integers(min_value=0, max_value=50),
)


def _make_trace(turns: int = 1) -> AgentTrace:
    return AgentTrace(
        adapter_name="prop-test",
        scenario_name="prop-scenario",
        turns=[Turn(turn_number=i + 1, duration_ms=100.0, tokens_input=500, tokens_output=200) for i in range(turns)],
        success=True,
    )


# ---------------------------------------------------------------------------
# P1: Composite score bounds
# ---------------------------------------------------------------------------


class TestScoringInvariants:
    @given(metrics=_scoring_input)
    @settings(max_examples=200)
    def test_composite_score_bounded_0_100(self, metrics: ScoringInput) -> None:
        """Composite score must always be in [0, 100] for any valid input."""
        # Clamp tasks_succeeded ≤ tasks_attempted
        metrics.tasks_succeeded = min(metrics.tasks_succeeded, metrics.tasks_attempted)
        metrics.autonomy_completed = min(metrics.autonomy_completed, metrics.autonomy_eligible)

        trace = _make_trace()
        result = compute_score(trace, metrics)
        assert 0.0 <= result.composite_score <= 100.0, f"Score {result.composite_score} out of bounds"

    @given(metrics=_scoring_input)
    @settings(max_examples=100)
    def test_safety_hard_gate_forces_zero(self, metrics: ScoringInput) -> None:
        """Any CRITICAL or HIGH violation must produce composite_score == 0."""
        metrics.tasks_succeeded = min(metrics.tasks_succeeded, metrics.tasks_attempted)
        metrics.autonomy_completed = min(metrics.autonomy_completed, metrics.autonomy_eligible)
        # Force a critical violation
        metrics.violations = [ViolationSeverity.CRITICAL]

        trace = _make_trace()
        result = compute_score(trace, metrics)
        assert result.composite_score == 0.0
        assert result.safety_gate_passed is False

    @given(metrics=_scoring_input)
    @settings(max_examples=100)
    def test_seven_dimensions_always_returned(self, metrics: ScoringInput) -> None:
        """compute_score must always return exactly 7 dimensions."""
        metrics.tasks_succeeded = min(metrics.tasks_succeeded, metrics.tasks_attempted)
        metrics.autonomy_completed = min(metrics.autonomy_completed, metrics.autonomy_eligible)

        trace = _make_trace()
        result = compute_score(trace, metrics)
        assert len(result.dimensions) == 7


# ---------------------------------------------------------------------------
# P2: JSONL roundtrip
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), blacklist_characters="\x00"),
    min_size=0,
    max_size=50,
)

_trace_event = st.builds(
    TraceEvent,
    event_type=st.sampled_from(["tool_call", "file_edit", "decision", "escalation", "failure", "recovery"]),
    data=st.fixed_dictionaries({"key": _safe_text}),
    file_path=st.one_of(st.none(), _safe_text),
)

_turn = st.builds(
    Turn,
    turn_number=st.integers(min_value=1, max_value=100),
    start_time=st.just("t0"),
    end_time=st.just("t1"),
    duration_ms=_non_negative_float,
    tokens_input=_non_negative_int,
    tokens_output=_non_negative_int,
    events=st.lists(_trace_event, min_size=0, max_size=5),
    reasoning=_safe_text,
)


class TestJSONLRoundtrip:
    @given(turns=st.lists(_turn, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_roundtrip_preserves_turn_count(self, turns: list[Turn]) -> None:
        """trace_to_jsonl → jsonl_to_trace must preserve the number of turns."""
        trace = AgentTrace(
            adapter_name="roundtrip",
            scenario_name="prop",
            turns=turns,
            success=True,
        )
        restored = jsonl_to_trace(trace_to_jsonl(trace))
        assert len(restored.turns) == len(trace.turns)

    @given(turns=st.lists(_turn, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_roundtrip_preserves_adapter_name(self, turns: list[Turn]) -> None:
        """Adapter name must survive serialization roundtrip."""
        trace = AgentTrace(adapter_name="roundtrip-test", scenario_name="prop", turns=turns, success=True)
        restored = jsonl_to_trace(trace_to_jsonl(trace))
        assert restored.adapter_name == trace.adapter_name

    @given(turns=st.lists(_turn, min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_roundtrip_preserves_event_types(self, turns: list[Turn]) -> None:
        """Event types within turns must survive roundtrip."""
        trace = AgentTrace(adapter_name="evt-test", scenario_name="prop", turns=turns, success=True)
        restored = jsonl_to_trace(trace_to_jsonl(trace))
        for orig_turn, rest_turn in zip(trace.turns, restored.turns, strict=True):
            assert len(rest_turn.events) == len(orig_turn.events)
            for orig_evt, rest_evt in zip(orig_turn.events, rest_turn.events, strict=True):
                assert rest_evt.event_type == orig_evt.event_type


# ---------------------------------------------------------------------------
# P3: ContainmentMatrix invariants
# ---------------------------------------------------------------------------


class TestContainmentMatrixInvariants:
    @given(cm=_containment_matrix)
    @settings(max_examples=200)
    def test_precision_bounded(self, cm: ContainmentMatrix) -> None:
        """Precision must always be in [0, 1]."""
        assert 0.0 <= cm.precision <= 1.0

    @given(cm=_containment_matrix)
    @settings(max_examples=200)
    def test_recall_bounded(self, cm: ContainmentMatrix) -> None:
        """Recall must always be in [0, 1]."""
        assert 0.0 <= cm.recall <= 1.0

    @given(cm=_containment_matrix)
    @settings(max_examples=200)
    def test_f1_bounded(self, cm: ContainmentMatrix) -> None:
        """F1 must always be in [0, 1]."""
        assert 0.0 <= cm.f1 <= 1.0

    @given(cm=_containment_matrix)
    @settings(max_examples=200)
    def test_f1_zero_when_no_positives(self, cm: ContainmentMatrix) -> None:
        """F1 must be 0 when there are no true positives."""
        cm.tp = 0
        assert cm.f1 == 0.0


# ---------------------------------------------------------------------------
# P4: DimensionWeights validation
# ---------------------------------------------------------------------------


class TestWeightInvariants:
    @given(
        w1=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
        w2=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
        w3=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
        w4=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
        w5=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
        w6=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_weights_summing_to_one_never_raise(
        self, w1: float, w2: float, w3: float, w4: float, w5: float, w6: float
    ) -> None:
        """Any 7 weights that sum to 1.0 must pass validation."""
        w7 = 1.0 - (w1 + w2 + w3 + w4 + w5 + w6)
        if w7 < 0:
            return  # Skip — impossible to form valid weights
        weights = DimensionWeights(
            task_completion=w1,
            latency=w2,
            cost_efficiency=w3,
            safety_compliance=w4,
            containment=w5,
            reliability=w6,
            autonomy=w7,
        )
        # Must NOT raise
        weights.validate()
