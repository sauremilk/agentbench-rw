"""Report generator — Markdown + SVG from evaluation results.

Supports:
  - Single-run reports with radar chart
  - Multi-run comparison reports (e.g. policy v0 vs v1 vs v2)
  - RunResult-aware report generation with verification details
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agentbench.report.radar import render_radar_svg
from agentbench.types import DimensionResult, EvalResult

if TYPE_CHECKING:
    from agentbench.runner import RunResult


def generate_markdown_report(result: EvalResult) -> str:
    """Generate a complete Markdown evaluation report.

    Args:
        result: The evaluation result from scoring.compute_score().

    Returns:
        Markdown string ready for file output or display.
    """
    lines: list[str] = []
    trace = result.trace

    # Header
    lines.append("# AgentBench-RW Evaluation Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Trace ID:** {trace.trace_id}")
    lines.append(f"**Adapter:** {trace.adapter_name}")
    lines.append(f"**Scenario:** {trace.scenario_name}")
    lines.append("")

    # Composite score
    _append_composite_section(lines, result)

    # Dimension breakdown
    _append_dimensions_table(lines, result.dimensions)

    # Safety details (if violations)
    safety = _find_dimension(result.dimensions, "safety")
    if safety and safety.details:
        _append_safety_section(lines, safety)

    # Failure breakdown
    _append_failures_section(lines, result)

    return "\n".join(lines)


def _find_dimension(
    dimensions: list[DimensionResult],
    name: str,
) -> DimensionResult | None:
    """Find a dimension by name."""
    for d in dimensions:
        if d.name == name:
            return d
    return None


def _append_composite_section(lines: list[str], result: EvalResult) -> None:
    score = result.composite_score
    grade = _score_to_grade(score)
    emoji = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"

    lines.append("## Composite Score")
    lines.append("")
    lines.append(f"### {emoji} {score:.1f} / 100 — Grade: **{grade}**")
    lines.append("")

    if score == 0 and any(d.details.get("has_critical_violations") for d in result.dimensions if d.details):
        lines.append("> ⚠️ **Safety Hard Gate triggered** — critical/high violations detected.")
        lines.append("> Composite score forced to 0 regardless of other dimensions.")
        lines.append("")


def _append_dimensions_table(
    lines: list[str],
    dimensions: list[DimensionResult],
) -> None:
    lines.append("## Dimension Breakdown")
    lines.append("")
    lines.append("| Dimension | Score | Weighted | Pass |")
    lines.append("|-----------|-------|----------|------|")

    for dim in dimensions:
        passed = "✅" if dim.passed else "❌"
        lines.append(f"| {dim.name.title()} | {dim.raw_score:.2f} | {dim.weighted_score:.3f} | {passed} |")
    lines.append("")


def _append_safety_section(lines: list[str], safety: DimensionResult) -> None:
    lines.append("## Safety Details")
    lines.append("")
    violations = safety.details.get("violations", [])
    if isinstance(violations, list):
        for v in violations:
            if isinstance(v, dict):
                sev = v.get("severity", "unknown")
                desc = v.get("description", "")
                lines.append(f"- **{sev}:** {desc}")
            else:
                lines.append(f"- {v}")
    lines.append("")


def _append_failures_section(lines: list[str], result: EvalResult) -> None:
    reliability = _find_dimension(result.dimensions, "reliability")
    if not reliability or not reliability.details:
        return

    details = reliability.details
    total = details.get("total_failures", 0)
    if total == 0:
        return

    lines.append("## Failure Summary")
    lines.append("")
    lines.append(f"**Total failures:** {total}")
    recovery = details.get("recovery_rate")
    if recovery is not None:
        lines.append(f"**Recovery rate:** {recovery:.0%}")
    lines.append("")

    breakdown = details.get("breakdown", {})
    if isinstance(breakdown, dict) and breakdown:
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, count in sorted(breakdown.items()):
            lines.append(f"| {cat} | {count} |")
        lines.append("")


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def generate_report_with_radar(
    result: EvalResult,
    output_dir: Path,
    *,
    filename_prefix: str = "eval",
) -> tuple[Path, Path]:
    """Generate both Markdown report and SVG radar chart.

    Args:
        result: Evaluation result.
        output_dir: Directory to write files to.
        filename_prefix: Prefix for output files.

    Returns:
        Tuple of (markdown_path, svg_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build scores dict for radar
    scores = {dim.name: dim.raw_score for dim in result.dimensions}

    # Radar SVG
    svg = render_radar_svg(
        scores,
        title=f"Agent: {result.trace.adapter_name} — Score: {result.composite_score:.0f}/100",
    )
    svg_path = output_dir / f"{filename_prefix}_radar.svg"
    svg_path.write_text(svg, encoding="utf-8")

    # Markdown report
    md = generate_markdown_report(result)
    # Embed radar reference
    md = md.replace(
        "## Composite Score",
        f"![Radar Chart]({svg_path.name})\n\n## Composite Score",
    )
    md_path = output_dir / f"{filename_prefix}_report.md"
    md_path.write_text(md, encoding="utf-8")

    return md_path, svg_path


# ---------------------------------------------------------------------------
# RunResult-aware report (includes verification details)
# ---------------------------------------------------------------------------


def generate_run_report(run_result: RunResult) -> str:
    """Generate a Markdown report from a RunResult including verification checks.

    Args:
        run_result: Complete result from runner.run_scenario().

    Returns:
        Markdown string with verification section appended.
    """
    md = generate_markdown_report(run_result.eval_result)
    lines = md.split("\n")

    # Insert verification section before the end
    ver_lines: list[str] = []
    ver_lines.append("## Verification Checks")
    ver_lines.append("")
    ver_lines.append(f"**Scenario:** {run_result.scenario_name}")
    ver_lines.append(f"**Adapter:** {run_result.adapter_name}")
    ver_lines.append(f"**Passed:** {'✅' if run_result.verification.passed else '❌'}")
    ver_lines.append("")

    checks = run_result.verification.checks
    if checks:
        ver_lines.append("| Check | Result |")
        ver_lines.append("|-------|--------|")
        for check_name, check_passed in checks.items():
            status = "✅" if check_passed else "❌"
            ver_lines.append(f"| {check_name} | {status} |")
        ver_lines.append("")

    lines.extend(ver_lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Comparison report (multi-run, e.g. policy v0 vs v1 vs v2)
# ---------------------------------------------------------------------------


def generate_comparison_report(
    results: list[RunResult],
    *,
    title: str = "Policy Comparison",
    labels: list[str] | None = None,
) -> str:
    """Generate a Markdown comparison table from multiple RunResults.

    Args:
        results: List of RunResults to compare.
        title: Report title.
        labels: Optional labels for each result (e.g. ["v0", "v1", "v2"]).
            Defaults to adapter names.

    Returns:
        Markdown string with comparison tables.
    """
    if not results:
        return f"# {title}\n\nNo results to compare."

    tags = labels or [r.adapter_name for r in results]
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Variants:** {len(results)}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    header = "| Metric |" + "|".join(f" {t} " for t in tags) + "|"
    sep = "|--------|" + "|".join("------" for _ in tags) + "|"
    lines.append(header)
    lines.append(sep)

    def _row(name: str, values: list[str]) -> str:
        return f"| {name} |" + "|".join(f" {v} " for v in values) + "|"

    lines.append(_row("Composite Score", [f"{r.composite_score:.1f}" for r in results]))
    lines.append(_row("Safety Gate", ["✅" if r.eval_result.safety_gate_passed else "❌" for r in results]))
    lines.append(_row("Verification", ["✅" if r.verification.passed else "❌" for r in results]))
    lines.append(_row("Turns", [str(len(r.trace.turns)) for r in results]))
    lines.append(_row("Tokens", [str(r.trace.total_tokens) for r in results]))
    lines.append("")

    # Dimension comparison
    lines.append("## Dimension Breakdown")
    lines.append("")
    dim_header = "| Dimension |" + "|".join(f" {t} " for t in tags) + "|"
    dim_sep = "|-----------|" + "|".join("------" for _ in tags) + "|"
    lines.append(dim_header)
    lines.append(dim_sep)

    # Collect all dimension names from first result
    dim_names = [d.name for d in results[0].eval_result.dimensions]
    for dname in dim_names:
        scores: list[str] = []
        for r in results:
            dim = _find_dimension(r.eval_result.dimensions, dname)
            scores.append(f"{dim.raw_score:.2f}" if dim else "—")
        lines.append(_row(dname.title(), scores))
    lines.append("")

    # Containment comparison (most important for policy tuning)
    lines.append("## Containment Details")
    lines.append("")
    cont_header = "| Metric |" + "|".join(f" {t} " for t in tags) + "|"
    cont_sep = "|--------|" + "|".join("------" for _ in tags) + "|"
    lines.append(cont_header)
    lines.append(cont_sep)

    for metric_name in ("precision", "recall", "f1", "false_negative_rate"):
        values: list[str] = []
        for r in results:
            if r.eval_result.containment:
                val = getattr(r.eval_result.containment, metric_name, None)
                values.append(f"{val:.3f}" if val is not None else "—")
            else:
                values.append("—")
        lines.append(_row(metric_name.replace("_", " ").title(), values))
    lines.append("")

    # Delta column (first vs last)
    if len(results) >= 2:
        first = results[0]
        last = results[-1]
        lines.append("## Delta (First → Last)")
        lines.append("")
        delta_score = last.composite_score - first.composite_score
        pct = (delta_score / first.composite_score * 100) if first.composite_score > 0 else 0
        lines.append(f"- **Composite Score:** {first.composite_score:.1f} → {last.composite_score:.1f} ({pct:+.0f}%)")

        if first.eval_result.containment and last.eval_result.containment:
            c0 = first.eval_result.containment
            c1 = last.eval_result.containment
            lines.append(f"- **Recall:** {c0.recall:.3f} → {c1.recall:.3f}")
            lines.append(f"- **F1:** {c0.f1:.3f} → {c1.f1:.3f}")
            lines.append(f"- **FN Rate:** {c0.false_negative_rate:.3f} → {c1.false_negative_rate:.3f}")
        lines.append("")

    return "\n".join(lines)


def generate_comparison_with_radar(
    results: list[RunResult],
    output_dir: Path,
    *,
    title: str = "Policy Comparison",
    labels: list[str] | None = None,
    colors: list[str] | None = None,
) -> tuple[Path, list[Path]]:
    """Generate comparison report with individual radar charts per variant.

    Returns:
        Tuple of (report_path, list_of_svg_paths).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    tags = labels or [r.adapter_name for r in results]
    palette = colors or ["#4A90D9", "#E85D3A", "#5BC236", "#9B59B6", "#F4A623"]

    svg_paths: list[Path] = []
    for i, (result, tag) in enumerate(zip(results, tags)):
        color = palette[i % len(palette)]
        scores = {d.name: d.raw_score for d in result.eval_result.dimensions}
        svg = render_radar_svg(
            scores,
            title=f"{tag} — {result.composite_score:.0f}/100",
            color=color,
        )
        svg_path = output_dir / f"radar_{tag}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        svg_paths.append(svg_path)

    md = generate_comparison_report(results, title=title, labels=tags)
    # Embed radar references
    radar_refs = "\n".join(f"![{tag}]({p.name})" for tag, p in zip(tags, svg_paths))
    md = f"{radar_refs}\n\n{md}"

    md_path = output_dir / "comparison_report.md"
    md_path.write_text(md, encoding="utf-8")
    return md_path, svg_paths
