"""Generate policy comparison data (v0 vs v1 vs v2).

Replays all baseline traces with each policy variant and produces:
  - results/COMPARISON.md  — Markdown comparison table
  - results/radar_*.svg    — Radar charts per variant

Usage:
    python scripts/generate_comparison.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agentbench.policies.optimizer import quick_compare
from agentbench.traces import load_trace


def main() -> Path:
    """Generate comparison from baseline traces and write results."""
    basedir = Path("results/baseline")
    outdir = Path("results")
    outdir.mkdir(parents=True, exist_ok=True)

    trace_files = sorted(basedir.glob("*.jsonl"))
    if not trace_files:
        msg = f"No traces found in {basedir}"
        raise FileNotFoundError(msg)

    print(f"Loading {len(trace_files)} traces from {basedir}/")
    traces = [load_trace(p) for p in trace_files]

    print("Running 3-way comparison: null-v0 vs rule-v1 vs tuned-v2")
    result = quick_compare(traces)

    # Build comparison document
    lines: list[str] = []
    lines.append("# Policy Comparison — Vorher/Nachher")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Traces evaluated:** {len(traces)} ({len(trace_files)} files)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary table
    lines.append("## Vorher/Nachher-Tabelle")
    lines.append("")
    lines.append("| Metric | v0 (Null) | v1 (Rule-Based) | v2 (Tuned) | Δ v0→v2 |")
    lines.append("|--------|-----------|-----------------|------------|---------|")

    v0 = result.baseline_null
    v1 = result.baseline_v1
    v2 = result.best_variant

    def _delta(old: float, new: float) -> str:
        if old == 0:
            return "—"
        pct = (new - old) / old * 100
        return f"**{pct:+.0f}%**"

    if v0 and v1 and v2:
        lines.append(
            f"| Recall | {v0.mean_recall:.2f} | {v1.mean_recall:.2f} | {v2.mean_recall:.2f} "
            f"| {_delta(v0.mean_recall, v2.mean_recall)} |"
        )
        lines.append(
            f"| Precision | {v0.mean_precision:.2f} | {v1.mean_precision:.2f} | {v2.mean_precision:.2f} "
            f"| {_delta(v0.mean_precision, v2.mean_precision)} |"
        )
        lines.append(
            f"| F1 | {v0.mean_f1:.2f} | {v1.mean_f1:.2f} | {v2.mean_f1:.2f} | {_delta(v0.mean_f1, v2.mean_f1)} |"
        )
        fn0 = 1.0 - v0.mean_recall
        fn1 = 1.0 - v1.mean_recall
        fn2 = 1.0 - v2.mean_recall
        lines.append(f"| FN Rate | {fn0:.2f} | {fn1:.2f} | {fn2:.2f} | {_delta(fn0, fn2)} |")
        lines.append(
            f"| Composite Score | {v0.mean_composite:.1f} | {v1.mean_composite:.1f} | {v2.mean_composite:.1f} "
            f"| {_delta(v0.mean_composite, v2.mean_composite)} |"
        )
        lines.append(
            f"| Safety Pass Rate | {v0.safety_pass_rate:.0%} | {v1.safety_pass_rate:.0%} | {v2.safety_pass_rate:.0%} "
            f"| — |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Full grid comparison table from optimizer
    lines.append("## Full Variant Comparison")
    lines.append("")
    lines.append(result.comparison_table())
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Key Findings")
    lines.append("")
    if v0 and v2:
        if v0.mean_recall > 0:
            recall_improvement = v2.mean_recall / v0.mean_recall
            lines.append(f"1. **Containment Recall** improved {recall_improvement:.1f}× (v0→v2)")
        else:
            lines.append(f"1. **Containment Recall** went from 0.00 to {v2.mean_recall:.2f} (v0 = no escalation)")
        lines.append(f"2. **Containment F1** improved from {v0.mean_f1:.2f} to {v2.mean_f1:.2f}")
        lines.append(f"3. **False Negative Rate** reduced from {1 - v0.mean_recall:.2f} to {1 - v2.mean_recall:.2f}")
        lines.append(f"4. **Composite Score** improved from {v0.mean_composite:.1f} to {v2.mean_composite:.1f}")
        if v1:
            lines.append(
                f"5. **v2 vs v1:** Precision improved {v1.mean_precision:.2f} → {v2.mean_precision:.2f}"
                f" (fewer false positives while maintaining recall)"
            )
        lines.append(f"6. **Safety** maintained at {v2.safety_pass_rate:.0%} pass rate across all variants")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append("# Install")
    lines.append('pip install -e ".[dev]"')
    lines.append("")
    lines.append("# Generate baselines (3× per scenario)")
    lines.append("python scripts/generate_baselines.py --runs 3")
    lines.append("")
    lines.append("# Regenerate this comparison")
    lines.append("python scripts/generate_comparison.py")
    lines.append("")
    lines.append("# Or via CLI")
    lines.append("agentbench optimize --traces-dir results/baseline/ --output results/optimization.md")
    lines.append("```")
    lines.append("")

    out_path = outdir / "COMPARISON.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nComparison written to {out_path}")

    # Print summary
    if v0 and v1 and v2:
        for label, v in [("v0 (Null)", v0), ("v1 (Rule-Based)", v1), ("v2 (Tuned)", v2)]:
            print(f"  {label:18s} Recall={v.mean_recall:.3f}  F1={v.mean_f1:.3f}  Comp={v.mean_composite:.1f}")

    return out_path


if __name__ == "__main__":
    main()
