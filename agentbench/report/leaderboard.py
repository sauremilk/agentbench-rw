"""Leaderboard generator — cross-adapter ranking from baseline traces.

Generates a Markdown leaderboard table ranking adapters by composite score
across all scenarios. Supports per-adapter aggregation, per-scenario detail,
dimension heatmaps, and best-practices extraction from failure taxonomy.

Zero external dependencies — pure Python + string formatting.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from agentbench.runner import RunResult


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------


def _aggregate_by_adapter(results: list[RunResult]) -> dict[str, list[RunResult]]:
    """Group RunResults by adapter name."""
    groups: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        groups[r.adapter_name].append(r)
    return dict(groups)


def _adapter_avg_score(results: list[RunResult]) -> float:
    """Average composite score across scenarios for one adapter."""
    if not results:
        return 0.0
    return sum(r.composite_score for r in results) / len(results)


def _adapter_pass_rate(results: list[RunResult]) -> float:
    """Fraction of scenarios that passed verification."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def _dimension_scores(results: list[RunResult]) -> dict[str, float]:
    """Average raw score per dimension across results."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        for dim in r.eval_result.dimensions:
            totals[dim.name] += dim.raw_score
            counts[dim.name] += 1
    return {name: totals[name] / counts[name] for name in totals}


# ---------------------------------------------------------------------------
# Markdown table builders
# ---------------------------------------------------------------------------


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _score_emoji(score: float) -> str:
    if score >= 85:
        return "🟢"
    if score >= 70:
        return "🟡"
    return "🔴"


def generate_leaderboard(
    results: list[RunResult],
    *,
    title: str = "AgentBench-RW Leaderboard",
) -> str:
    """Generate a full leaderboard Markdown document.

    Sections:
    1. Rankings table (adapters ranked by avg composite score)
    2. Per-scenario breakdown
    3. Dimension heatmap (adapter × dimension)
    4. Containment matrix summary
    5. Best practices from scoring patterns
    """
    groups = _aggregate_by_adapter(results)
    # Sort by avg score descending
    ranked = sorted(groups.items(), key=lambda kv: _adapter_avg_score(kv[1]), reverse=True)

    lines: list[str] = []

    # Header
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"*Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append(f"*Adapters: {len(ranked)} | Scenarios: {len(results)} | Dimensions: 7*")
    lines.append("")

    # --- Section 1: Rankings ---
    _append_rankings(lines, ranked)

    # --- Section 2: Per-scenario ---
    _append_scenario_breakdown(lines, results)

    # --- Section 3: Dimension heatmap ---
    _append_dimension_heatmap(lines, ranked)

    # --- Section 4: Containment summary ---
    _append_containment_summary(lines, ranked)

    # --- Section 5: Best practices ---
    _append_best_practices(lines, ranked)

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Powered by [AgentBench-RW](https://github.com/sauremilk/agentbench-rw) — ")
    lines.append("7-dimension evaluation for real-world AI agents.*")
    lines.append("")

    return "\n".join(lines)


def _append_rankings(lines: list[str], ranked: list[tuple[str, list[RunResult]]]) -> None:
    lines.append("## 🏆 Rankings")
    lines.append("")
    lines.append("| Rank | Adapter | Avg Score | Grade | Pass Rate | Scenarios | Safety |")
    lines.append("|:----:|---------|:---------:|:-----:|:---------:|:---------:|:------:|")

    for i, (adapter, runs) in enumerate(ranked, 1):
        avg = _adapter_avg_score(runs)
        grade = _grade(avg)
        emoji = _score_emoji(avg)
        pass_rate = _adapter_pass_rate(runs)
        safety_ok = all(r.eval_result.safety_gate_passed for r in runs)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, str(i))

        lines.append(
            f"| {medal} | **{adapter}** | {emoji} {avg:.1f} | {grade} "
            f"| {pass_rate:.0%} | {len(runs)} | {'✅' if safety_ok else '❌'} |"
        )
    lines.append("")


def _append_scenario_breakdown(lines: list[str], results: list[RunResult]) -> None:
    lines.append("## 📊 Per-Scenario Breakdown")
    lines.append("")
    lines.append("| Adapter | Scenario | Score | Zone | Turns | Passed | Safety |")
    lines.append("|---------|----------|:-----:|:----:|:-----:|:------:|:------:|")

    for r in sorted(results, key=lambda x: (x.adapter_name, x.scenario_name)):
        # Determine zone from scenario name heuristic
        zone = _infer_zone(r)
        passed = "✅" if r.passed else "❌"
        safety = "✅" if r.eval_result.safety_gate_passed else "❌"
        lines.append(
            f"| {r.adapter_name} | {r.scenario_name} | {r.composite_score:.1f} "
            f"| {zone} | {len(r.trace.turns)} | {passed} | {safety} |"
        )
    lines.append("")


def _infer_zone(r: RunResult) -> str:
    """Heuristic: infer zone emoji from scenario name or trace events."""
    name = r.scenario_name.lower()
    if "critical" in name or "escalation" in name or "safety" in name or "s3" in name:
        return "🔴"
    if "sensitive" in name or "multi" in name or "retry" in name or "s2" in name:
        return "🟡"
    return "🟢"


def _append_dimension_heatmap(
    lines: list[str],
    ranked: list[tuple[str, list[RunResult]]],
) -> None:
    lines.append("## 🎯 Dimension Heatmap (Avg per Adapter)")
    lines.append("")

    dim_names = [
        "task_completion",
        "latency",
        "cost",
        "safety",
        "containment",
        "reliability",
        "autonomy",
    ]
    short = ["D1 Compl.", "D2 Latency", "D3 Cost", "D4 Safety", "D5 Contain.", "D6 Reliab.", "D7 Auton."]

    header = "| Adapter |" + "|".join(f" {s} " for s in short) + "|"
    sep = "|---------|" + "|".join(":------:" for _ in short) + "|"
    lines.append(header)
    lines.append(sep)

    for adapter, runs in ranked:
        dim_avg = _dimension_scores(runs)
        cells: list[str] = []
        for dn in dim_names:
            val = dim_avg.get(dn, 0.0)
            # Color indicator
            indicator = "🟢" if val >= 0.8 else "🟡" if val >= 0.5 else "🔴"
            cells.append(f"{indicator} {val:.0%}")
        lines.append(f"| **{adapter}** |" + "|".join(f" {c} " for c in cells) + "|")
    lines.append("")


def _append_containment_summary(
    lines: list[str],
    ranked: list[tuple[str, list[RunResult]]],
) -> None:
    lines.append("## 🛡️ Containment Summary")
    lines.append("")
    lines.append("| Adapter | Precision | Recall | F1 | FN Rate |")
    lines.append("|---------|:---------:|:------:|:--:|:-------:|")

    for adapter, runs in ranked:
        # Aggregate containment across scenarios
        tp = fp = tn = fn = 0
        for r in runs:
            cm = r.eval_result.containment
            if cm:
                tp += cm.tp
                fp += cm.fp
                tn += cm.tn
                fn += cm.fn
        total = tp + fp + tn + fn
        if total == 0:
            lines.append(f"| {adapter} | — | — | — | — |")
            continue
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        lines.append(f"| {adapter} | {prec:.3f} | {rec:.3f} | {f1:.3f} | {fnr:.3f} |")
    lines.append("")


def _append_best_practices(
    lines: list[str],
    ranked: list[tuple[str, list[RunResult]]],
) -> None:
    lines.append("## 💡 Key Insights")
    lines.append("")

    if not ranked:
        lines.append("No results to analyze.")
        lines.append("")
        return

    best_adapter, best_runs = ranked[0]
    best_avg = _adapter_avg_score(best_runs)

    lines.append(f"1. **Top performer: {best_adapter}** with avg score {best_avg:.1f}/100")

    # Safety across all
    all_safe = all(r.eval_result.safety_gate_passed for _, runs in ranked for r in runs)
    if all_safe:
        lines.append("2. **Safety gate**: 100% pass rate across all adapters — no critical violations")
    else:
        lines.append("2. **Safety gate**: Some adapters triggered safety violations — review D4 scores")

    # Hardest scenario
    all_results = [r for _, runs in ranked for r in runs]
    if all_results:
        hardest = min(all_results, key=lambda r: r.composite_score)
        lines.append(
            f"3. **Hardest scenario**: `{hardest.scenario_name}` "
            f"(score: {hardest.composite_score:.1f}, adapter: {hardest.adapter_name})"
        )

    # Containment insight
    lines.append(
        "4. **Containment F1** is the key differentiator between policy versions — "
        "replay baselines with `agentbench compare` to see v0→v2 progression"
    )

    # Replay tip
    lines.append(
        "5. **Reproduce**: All scores are deterministic — "
        "`agentbench run --adapter <name> --scenario <name> --mode replay`"
    )
    lines.append("")


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------


def write_leaderboard(
    results: list[RunResult],
    output_path: Path,
    *,
    title: str = "AgentBench-RW Leaderboard",
) -> Path:
    """Generate and write LEADERBOARD.md."""
    md = generate_leaderboard(results, title=title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    return output_path
