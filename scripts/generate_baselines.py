"""Generate baseline traces for all scenarios.

Usage:
    python scripts/generate_baselines.py              # 1 run per scenario (default)
    python scripts/generate_baselines.py --runs 3     # 3 runs per scenario
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agentbench.adapters.autogen.adapter import AutoGenAdapter
from agentbench.adapters.langgraph.adapter import LangGraphAdapter
from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.runner import run_scenario
from agentbench.scenarios.registry import get_registry

SCENARIO_ADAPTERS: dict[str, type] = {
    "orchestrator_s1_solo_bugfix": OrchestratorAdapter,
    "orchestrator_s2_multi_file_feature": OrchestratorAdapter,
    "orchestrator_s3_crossteam_escalation": OrchestratorAdapter,
    "langgraph_s1_classify_route": LangGraphAdapter,
    "langgraph_s2_multi_agent": LangGraphAdapter,
    "langgraph_s3_error_recovery": LangGraphAdapter,
    "autogen_s1_function_call": AutoGenAdapter,
    "autogen_s2_multi_agent_debate": AutoGenAdapter,
    "autogen_s3_safety_critical": AutoGenAdapter,
}


def main(runs: int = 1) -> list[Path]:
    """Generate baseline traces.

    Args:
        runs: Number of runs per scenario.

    Returns:
        List of generated trace file paths.
    """
    registry = get_registry()
    basedir = Path("results/baseline")
    basedir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    for name, adapter_cls in SCENARIO_ADAPTERS.items():
        for run_idx in range(runs):
            adapter = adapter_cls()
            scenario = registry.get(name)
            result = run_scenario(adapter, scenario, trace_dir=basedir)
            s = result.summary()
            run_label = f"[{run_idx + 1}/{runs}]" if runs > 1 else ""
            print(
                f"  {name} {run_label}: score={s['composite_score']}, "
                f"passed={s['passed']}, turns={s['turns']}, safety={s['safety_gate']}"
            )
            for check_name, check_passed in s["checks"].items():
                status = "PASS" if check_passed else "FAIL"
                print(f"    {check_name}: {status}")

            # Find the most recently created trace file
            traces = sorted(basedir.glob(f"{adapter.name}_{scenario.config.name}_*.jsonl"))
            if traces:
                generated.append(traces[-1])

    print(f"\n{len(generated)} baseline traces saved to {basedir}/")
    return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate baseline traces")
    parser.add_argument("--runs", type=int, default=1, help="Runs per scenario (default: 1)")
    args = parser.parse_args()
    main(runs=args.runs)
