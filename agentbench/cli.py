"""CLI entry point for agentbench.

Usage:
    agentbench run   --adapter orchestrator --scenario s1_solo_bugfix [--mode live|replay]
    agentbench compare --traces-dir results/baseline/ [--policies v0,v1,v2]
    agentbench report  --trace results/baseline/run.jsonl [--output report.md]
    agentbench optimize --traces-dir results/baseline/ [--output optimization.md]
    agentbench list    [--adapters | --scenarios | --policies]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbench.adapters.base import BaseAdapter


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (registered as ``agentbench`` console_script)."""
    parser = argparse.ArgumentParser(
        prog="agentbench",
        description="Real-World Agent Evaluation Framework",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ──────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Run a scenario (live or replay)")
    p_run.add_argument("--adapter", required=True, choices=["orchestrator", "langgraph", "autogen", "tau2bench"])
    p_run.add_argument("--scenario", required=True, help="Scenario name (e.g. s1_solo_bugfix)")
    p_run.add_argument("--mode", default="live", choices=["live", "replay"])
    p_run.add_argument("--trace-file", type=Path, help="Trace file (required for replay mode)")
    p_run.add_argument("--output-dir", type=Path, default=Path("results"), help="Directory for trace output")
    p_run.add_argument("--report", action="store_true", help="Generate Markdown report after run")

    # ── compare ──────────────────────────────────────────────────────────
    p_cmp = sub.add_parser("compare", help="Compare traces with different policies")
    p_cmp.add_argument("--traces-dir", type=Path, required=True, help="Directory containing .jsonl traces")
    p_cmp.add_argument(
        "--policies",
        default="v0,v1,v2",
        help="Comma-separated policy versions (default: v0,v1,v2)",
    )
    p_cmp.add_argument("--output", type=Path, help="Output Markdown file")
    p_cmp.add_argument("--radar", action="store_true", help="Generate radar SVGs alongside report")

    # ── report ───────────────────────────────────────────────────────────
    p_rep = sub.add_parser("report", help="Generate report from a single trace")
    p_rep.add_argument("--trace", type=Path, required=True, help="Path to .jsonl trace file")
    p_rep.add_argument("--output", type=Path, help="Output Markdown file (default: stdout)")
    p_rep.add_argument("--radar", action="store_true", help="Include radar SVG")

    # ── optimize ─────────────────────────────────────────────────────────
    p_opt = sub.add_parser("optimize", help="Grid-search policy thresholds")
    p_opt.add_argument("--traces-dir", type=Path, required=True, help="Directory containing .jsonl traces")
    p_opt.add_argument("--output", type=Path, help="Output Markdown file")

    # ── list ─────────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", help="List available adapters, scenarios, or policies")
    p_list.add_argument("--adapters", action="store_true")
    p_list.add_argument("--scenarios", action="store_true")
    p_list.add_argument("--policies", action="store_true")

    # ── leaderboard ──────────────────────────────────────────────────────
    p_lb = sub.add_parser("leaderboard", help="Generate cross-adapter leaderboard from baselines")
    p_lb.add_argument(
        "--traces-dir",
        type=Path,
        default=Path("results/baseline"),
        help="Directory containing .jsonl baseline traces",
    )
    p_lb.add_argument("--output", type=Path, default=Path("docs/LEADERBOARD.md"), help="Output Markdown file")
    p_lb.add_argument("--radar", action="store_true", help="Generate radar SVGs per adapter")

    args = parser.parse_args(argv)

    handlers = {
        "run": _cmd_run,
        "compare": _cmd_compare,
        "report": _cmd_report,
        "optimize": _cmd_optimize,
        "list": _cmd_list,
        "leaderboard": _cmd_leaderboard,
    }
    return handlers[args.command](args)


# ─── Command handlers ───────────────────────────────────────────────────────


def _cmd_run(args: argparse.Namespace) -> int:
    from agentbench.runner import run_scenario
    from agentbench.scenarios.registry import get_registry
    from agentbench.types import RunMode

    registry = get_registry()
    scenario = registry.get(args.scenario)
    adapter = _make_adapter(args.adapter)
    mode = RunMode(args.mode)

    trace_file = args.trace_file if mode == RunMode.REPLAY else None
    result = run_scenario(
        adapter,
        scenario,
        mode=mode,
        trace_file=trace_file,
        trace_dir=args.output_dir,
    )

    _print_result_summary(result)

    if args.report:
        from agentbench.report.generator import generate_run_report

        report = generate_run_report(result)
        report_path = args.output_dir / f"{result.scenario_name}_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\nReport saved: {report_path}")

    return 0 if result.passed else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    from agentbench.policies.optimizer import quick_compare
    from agentbench.report.generator import generate_comparison_report, generate_comparison_with_radar
    from agentbench.runner import RunResult, run_scenario
    from agentbench.scenarios.registry import get_registry
    from agentbench.traces import load_trace
    from agentbench.types import RunMode

    traces = _load_traces(args.traces_dir)
    if not traces:
        print(f"No .jsonl traces found in {args.traces_dir}", file=sys.stderr)
        return 1

    # Quick 3-way comparison via optimizer
    opt_result = quick_compare(traces)

    print("\n" + opt_result.comparison_table())

    if args.output:
        # Build RunResults for report generator
        registry = get_registry()
        results: list[RunResult] = []
        labels: list[str] = []

        for trace_path in sorted(args.traces_dir.glob("*.jsonl")):
            trace = load_trace(trace_path)
            scenario_name = trace.scenario_name
            if scenario_name in registry:
                scenario = registry.get(scenario_name)
                r = run_scenario(
                    _make_adapter("orchestrator"),
                    scenario,
                    mode=RunMode.REPLAY,
                    trace_file=trace_path,
                )
                results.append(r)
                labels.append(trace_path.stem)

        if results:
            if args.radar:
                report_path, svg_paths = generate_comparison_with_radar(
                    results,
                    output_dir=args.output.parent,
                    title="Policy Comparison",
                    labels=labels,
                )
                print(f"\nComparison report: {report_path}")
                for svg in svg_paths:
                    print(f"  Radar: {svg}")
            else:
                report = generate_comparison_report(results, title="Policy Comparison", labels=labels)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(report, encoding="utf-8")
                print(f"\nComparison report: {args.output}")

    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from agentbench.report.generator import generate_report_with_radar
    from agentbench.traces import load_trace
    from agentbench.traces.replayer import replay_trace

    trace = load_trace(args.trace)
    eval_result = replay_trace(trace)

    if args.radar and args.output:
        md_path, svg_path = generate_report_with_radar(
            eval_result,
            output_dir=args.output.parent,
            filename_prefix=trace.scenario_name or "eval",
        )
        print(f"Report: {md_path}")
        print(f"Radar:  {svg_path}")
    else:
        from agentbench.report.generator import generate_markdown_report

        report = generate_markdown_report(eval_result)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            print(f"Report: {args.output}")
        else:
            print(report)

    return 0


def _cmd_optimize(args: argparse.Namespace) -> int:
    from agentbench.policies.optimizer import grid_search

    traces = _load_traces(args.traces_dir)
    if not traces:
        print(f"No .jsonl traces found in {args.traces_dir}", file=sys.stderr)
        return 1

    print("Running grid search (this may take a moment)...")
    result = grid_search(traces)

    print(f"\nBest params: {result.best_params}")
    print(f"Best F1:     {result.best_f1:.3f}")
    print(f"Variants:    {len(result.variants)}")
    print()
    print(result.comparison_table())

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        content = f"# Grid Search Results\n\n{result.comparison_table()}\n"
        args.output.write_text(content, encoding="utf-8")
        print(f"\nReport: {args.output}")

    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    if args.scenarios or not (args.adapters or args.policies):
        from agentbench.scenarios.registry import get_registry

        registry = get_registry()
        scenarios = registry.list_scenarios()
        print(f"Scenarios ({len(scenarios)}):")
        for s in scenarios:
            print(f"  - {s}")

    if args.adapters:
        print("Adapters:")
        print("  - orchestrator")
        print("  - langgraph")
        print("  - autogen")
        print("  - tau2bench")

    if args.policies:
        from agentbench.policies.escalation import NullPolicy, RuleBasedPolicy, TunedPolicy

        for p in [NullPolicy(), RuleBasedPolicy(), TunedPolicy()]:
            print(f"  - {p.name}")

    return 0


def _cmd_leaderboard(args: argparse.Namespace) -> int:
    from agentbench.report.leaderboard import write_leaderboard
    from agentbench.runner import RunResult, run_scenario
    from agentbench.scenarios.registry import get_registry
    from agentbench.traces import load_trace
    from agentbench.types import RunMode

    traces_dir: Path = args.traces_dir
    if not traces_dir.exists():
        print(f"Traces directory not found: {traces_dir}", file=sys.stderr)
        return 1

    trace_paths = sorted(traces_dir.glob("*.jsonl"))
    if not trace_paths:
        print(f"No .jsonl traces found in {traces_dir}", file=sys.stderr)
        return 1

    registry = get_registry()
    all_results: list[RunResult] = []

    for tp in trace_paths:
        trace = load_trace(tp)
        scenario_name = trace.scenario_name
        if scenario_name not in registry:
            continue
        scenario = registry.get(scenario_name)
        adapter = _make_adapter(trace.adapter_name)
        r = run_scenario(
            adapter,
            scenario,
            mode=RunMode.REPLAY,
            trace_file=tp,
        )
        all_results.append(r)

    # Deduplicate: keep only the latest trace per (adapter, scenario) pair.
    # trace_paths are sorted chronologically, so last wins.
    seen: dict[tuple[str, str], RunResult] = {}
    for r in all_results:
        seen[(r.adapter_name, r.scenario_name)] = r
    results: list[RunResult] = list(seen.values())

    if not results:
        print("No valid traces matched registered scenarios.", file=sys.stderr)
        return 1

    output_path: Path = args.output
    write_leaderboard(results, output_path)
    print(f"Leaderboard: {output_path} ({len(results)} scenarios, {len({r.adapter_name for r in results})} adapters)")

    if args.radar:
        from agentbench.report.radar import render_radar_svg

        radar_dir = output_path.parent / "radar"
        radar_dir.mkdir(parents=True, exist_ok=True)

        from collections import defaultdict

        groups: dict[str, list[RunResult]] = defaultdict(list)
        for r in results:
            groups[r.adapter_name].append(r)

        palette = ["#4A90D9", "#E85D3A", "#5BC236", "#9B59B6"]
        for i, (adapter, runs) in enumerate(sorted(groups.items())):
            dim_totals: dict[str, float] = defaultdict(float)
            dim_counts: dict[str, int] = defaultdict(int)
            for r in runs:
                for d in r.eval_result.dimensions:
                    dim_totals[d.name] += d.raw_score
                    dim_counts[d.name] += 1
            scores = {k: dim_totals[k] / dim_counts[k] for k in dim_totals}
            avg = sum(r.composite_score for r in runs) / len(runs)
            svg = render_radar_svg(
                scores,
                title=f"{adapter} — Avg {avg:.0f}/100",
                color=palette[i % len(palette)],
            )
            svg_path = radar_dir / f"radar_{adapter}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            print(f"  Radar: {svg_path}")

    return 0


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_adapter(name: str) -> BaseAdapter:
    """Lazy-create an adapter by name."""
    from agentbench.adapters.autogen.adapter import AutoGenAdapter
    from agentbench.adapters.langgraph.adapter import LangGraphAdapter
    from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
    from agentbench.adapters.tau2bench.adapter import TAU2BenchAdapter

    adapters: dict[str, type[BaseAdapter]] = {
        "orchestrator": OrchestratorAdapter,
        "langgraph": LangGraphAdapter,
        "autogen": AutoGenAdapter,
        "tau2bench": TAU2BenchAdapter,
    }
    if name not in adapters:
        msg = f"Unknown adapter: {name!r}"
        raise ValueError(msg)
    return adapters[name]()


def _load_traces(traces_dir: Path) -> list:
    """Load all .jsonl traces from a directory."""
    from agentbench.traces import load_trace

    paths = sorted(traces_dir.glob("*.jsonl"))
    return [load_trace(p) for p in paths]


def _print_result_summary(result: object) -> None:
    """Print a compact result summary to stdout."""
    summary = result.summary()  # type: ignore[attr-defined]
    status = "✅ PASSED" if summary["passed"] else "❌ FAILED"
    print(f"\n{status}  {summary['scenario']} ({summary['adapter']})")
    print(f"  Score:      {summary['composite_score']}")
    print(f"  Safety:     {'✅' if summary['safety_gate'] else '❌'}")
    print(f"  Turns:      {summary['turns']}")
    print(f"  Tokens:     {summary['tokens']}")
    print(f"  Duration:   {summary['duration_ms']} ms")
    if summary.get("checks"):
        print("  Checks:")
        for name, passed in summary["checks"].items():
            icon = "✅" if passed else "❌"
            print(f"    {icon} {name}")


if __name__ == "__main__":
    sys.exit(main())
