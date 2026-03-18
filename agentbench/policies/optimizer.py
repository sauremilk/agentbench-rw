"""Grid-search optimizer for escalation policy thresholds.

Replays recorded traces with varying policy parameters to find the
configuration that maximizes containment F1 score while maintaining safety.

Usage:
    from agentbench.policies.optimizer import grid_search, OptimizerResult
    from agentbench.traces import load_trace

    traces = [load_trace(p) for p in Path("results/baseline").glob("*.jsonl")]
    result = grid_search(traces)
    print(result.best_params)          # {'min_confidence': 0.45, 'budget_multiplier': 1.2, ...}
    print(result.best_f1)              # 0.68
    print(result.comparison_table())   # Markdown table of all variants
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentbench.policies.escalation import NullPolicy, RuleBasedPolicy, TunedPolicy
from agentbench.traces.replayer import replay_trace

if TYPE_CHECKING:
    from agentbench.config import EvalConfig
    from agentbench.types import AgentTrace, EvalResult

# Default search grids
_CONFIDENCE_GRID = [0.2, 0.3, 0.4, 0.45, 0.5, 0.6]
_BUDGET_GRID = [1.0, 1.2, 1.5, 2.0]
_RETRY_GRID = [1, 2, 3]


@dataclass
class PolicyVariant:
    """A single policy configuration evaluated on traces."""

    name: str
    params: dict[str, float | int]
    results: list[EvalResult] = field(default_factory=list)

    @property
    def mean_composite(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.composite_score for r in self.results) / len(self.results)

    @property
    def mean_f1(self) -> float:
        """Micro-averaged F1 across all traces (aggregated TP/FP/FN)."""
        tp = sum(r.containment.tp for r in self.results)
        fp = sum(r.containment.fp for r in self.results)
        fn = sum(r.containment.fn for r in self.results)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

    @property
    def mean_recall(self) -> float:
        """Micro-averaged recall across all traces."""
        tp = sum(r.containment.tp for r in self.results)
        fn = sum(r.containment.fn for r in self.results)
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def mean_precision(self) -> float:
        """Micro-averaged precision across all traces."""
        tp = sum(r.containment.tp for r in self.results)
        fp = sum(r.containment.fp for r in self.results)
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0

    @property
    def safety_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.safety_gate_passed) / len(self.results)


@dataclass
class OptimizerResult:
    """Complete result from a grid-search optimization run."""

    variants: list[PolicyVariant]
    best_variant: PolicyVariant
    baseline_null: PolicyVariant | None = None
    baseline_v1: PolicyVariant | None = None

    @property
    def best_params(self) -> dict[str, float | int]:
        return self.best_variant.params

    @property
    def best_f1(self) -> float:
        return self.best_variant.mean_f1

    def comparison_table(self) -> str:
        """Generate a Markdown comparison table of all variants."""
        lines = [
            "| Variant | Confidence | Budget | Retries | F1 | Recall | Precision | Composite | Safety |",
            "|---------|-----------|--------|---------|-----|--------|-----------|-----------|--------|",
        ]
        all_variants = []
        if self.baseline_null:
            all_variants.append(self.baseline_null)
        if self.baseline_v1:
            all_variants.append(self.baseline_v1)
        all_variants.extend(sorted(self.variants, key=lambda v: v.mean_f1, reverse=True))

        for v in all_variants:
            conf = v.params.get("min_confidence", "—")
            budget = v.params.get("budget_multiplier", "—")
            retries = v.params.get("max_retries", "—")
            safety = f"{v.safety_pass_rate:.0%}"
            best_marker = " **⬅ BEST**" if v is self.best_variant else ""
            lines.append(
                f"| {v.name}{best_marker} | {conf} | {budget} | {retries} "
                f"| {v.mean_f1:.3f} | {v.mean_recall:.3f} | {v.mean_precision:.3f} "
                f"| {v.mean_composite:.1f} | {safety} |"
            )
        return "\n".join(lines)


def _evaluate_policy_on_traces(
    policy_name: str,
    params: dict[str, float | int],
    traces: list[AgentTrace],
    config: EvalConfig | None = None,
    policy: NullPolicy | RuleBasedPolicy | TunedPolicy | None = None,
) -> PolicyVariant:
    """Replay all traces and collect results for one policy configuration."""
    variant = PolicyVariant(name=policy_name, params=dict(params))
    for trace in traces:
        result = replay_trace(trace, config=config, policy=policy)
        variant.results.append(result)
    return variant


def grid_search(
    traces: list[AgentTrace],
    *,
    confidence_grid: list[float] | None = None,
    budget_grid: list[float] | None = None,
    retry_grid: list[int] | None = None,
    config: EvalConfig | None = None,
    include_baselines: bool = True,
) -> OptimizerResult:
    """Run grid-search over policy thresholds to maximize containment F1.

    Args:
        traces: List of recorded AgentTraces to replay.
        confidence_grid: Confidence threshold values to try.
        budget_grid: Budget multiplier values to try.
        retry_grid: Max retry values to try.
        config: Evaluation config (weights, thresholds).
        include_baselines: Include null-v0 and rule-v1 as baselines.

    Returns:
        OptimizerResult with best variant, all variants, and baselines.
    """
    conf_values = confidence_grid or _CONFIDENCE_GRID
    budget_values = budget_grid or _BUDGET_GRID
    retry_values = retry_grid or _RETRY_GRID

    # Baselines
    baseline_null = None
    baseline_v1 = None
    if include_baselines:
        _null = NullPolicy()
        baseline_null = _evaluate_policy_on_traces(
            _null.name,
            {"min_confidence": 0, "budget_multiplier": 0, "max_retries": 0},
            traces,
            config,
            policy=_null,
        )
        _v1 = RuleBasedPolicy()
        baseline_v1 = _evaluate_policy_on_traces(
            _v1.name,
            {
                "min_confidence": _v1.min_confidence,
                "budget_multiplier": _v1.budget_multiplier,
                "max_retries": _v1.max_retries,
            },
            traces,
            config,
            policy=_v1,
        )

    # Grid search
    variants: list[PolicyVariant] = []
    for conf, budget, retries in itertools.product(conf_values, budget_values, retry_values):
        _policy = TunedPolicy(min_confidence=conf, budget_multiplier=budget, max_retries=retries)
        name = f"tuned(c={conf},b={budget},r={retries})"
        params = {"min_confidence": conf, "budget_multiplier": budget, "max_retries": retries}
        variant = _evaluate_policy_on_traces(name, params, traces, config, policy=_policy)
        variants.append(variant)

    # Find best by F1, break ties by composite score
    best = max(variants, key=lambda v: (v.mean_f1, v.mean_composite)) if variants else variants[0]

    return OptimizerResult(
        variants=variants,
        best_variant=best,
        baseline_null=baseline_null,
        baseline_v1=baseline_v1,
    )


def quick_compare(
    traces: list[AgentTrace],
    *,
    config: EvalConfig | None = None,
) -> OptimizerResult:
    """Quick 3-way comparison: null-v0 vs rule-v1 vs tuned-v2 (default params).

    Useful for generating the portfolio vorher/nachher table without a full grid search.
    """
    _null = NullPolicy()
    null_variant = _evaluate_policy_on_traces(
        _null.name,
        {"min_confidence": 0, "budget_multiplier": 0, "max_retries": 0},
        traces,
        config,
        policy=_null,
    )
    _v1 = RuleBasedPolicy()
    v1_variant = _evaluate_policy_on_traces(
        _v1.name,
        {
            "min_confidence": _v1.min_confidence,
            "budget_multiplier": _v1.budget_multiplier,
            "max_retries": _v1.max_retries,
        },
        traces,
        config,
        policy=_v1,
    )
    _v2 = TunedPolicy()
    v2_variant = _evaluate_policy_on_traces(
        _v2.name,
        {
            "min_confidence": _v2.min_confidence,
            "budget_multiplier": _v2.budget_multiplier,
            "max_retries": _v2.max_retries,
        },
        traces,
        config,
        policy=_v2,
    )

    return OptimizerResult(
        variants=[v2_variant],
        best_variant=v2_variant,
        baseline_null=null_variant,
        baseline_v1=v1_variant,
    )
