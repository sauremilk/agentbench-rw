"""Tests for leaderboard generation + CLI leaderboard command."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agentbench.adapters.orchestrator.adapter import OrchestratorAdapter
from agentbench.adapters.orchestrator.scenarios.s1_bugfix import S1SoloBugfix
from agentbench.report.leaderboard import (
    _adapter_avg_score,
    _adapter_pass_rate,
    _aggregate_by_adapter,
    _dimension_scores,
    _grade,
    _score_emoji,
    generate_leaderboard,
    write_leaderboard,
)
from agentbench.runner import RunResult, run_scenario

# ---------------------------------------------------------------------------
# Helper: build RunResults from real scenarios
# ---------------------------------------------------------------------------


def _make_results() -> list[RunResult]:
    """Run S1 across orchestrator to get at least one real RunResult."""
    adapter = OrchestratorAdapter()
    scenario = S1SoloBugfix()
    r1 = run_scenario(adapter, scenario)
    # Create a second result by modifying adapter name for multi-adapter testing
    r2 = run_scenario(adapter, scenario)
    r2.adapter_name = "test-adapter-b"
    return [r1, r2]


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestGrade:
    def test_grade_a(self) -> None:
        assert _grade(95.0) == "A"

    def test_grade_b(self) -> None:
        assert _grade(85.0) == "B"

    def test_grade_c(self) -> None:
        assert _grade(75.0) == "C"

    def test_grade_d(self) -> None:
        assert _grade(65.0) == "D"

    def test_grade_f(self) -> None:
        assert _grade(50.0) == "F"

    def test_grade_boundary_90(self) -> None:
        assert _grade(90.0) == "A"

    def test_grade_boundary_80(self) -> None:
        assert _grade(80.0) == "B"


class TestScoreEmoji:
    def test_green(self) -> None:
        assert "🟢" in _score_emoji(85.0)

    def test_yellow(self) -> None:
        assert "🟡" in _score_emoji(72.0)

    def test_red(self) -> None:
        assert "🔴" in _score_emoji(55.0)


class TestAggregation:
    def test_aggregate_by_adapter(self) -> None:
        results = _make_results()
        groups = _aggregate_by_adapter(results)
        assert len(groups) == 2
        assert "orchestrator" in groups
        assert "test-adapter-b" in groups

    def test_avg_score(self) -> None:
        results = _make_results()
        orch_results = [r for r in results if r.adapter_name == "orchestrator"]
        avg = _adapter_avg_score(orch_results)
        assert 0 < avg <= 100

    def test_avg_score_empty(self) -> None:
        assert _adapter_avg_score([]) == 0.0

    def test_pass_rate(self) -> None:
        results = _make_results()
        rate = _adapter_pass_rate(results)
        assert 0.0 <= rate <= 1.0

    def test_pass_rate_empty(self) -> None:
        assert _adapter_pass_rate([]) == 0.0

    def test_dimension_scores(self) -> None:
        results = _make_results()
        orch_results = [r for r in results if r.adapter_name == "orchestrator"]
        dims = _dimension_scores(orch_results)
        assert isinstance(dims, dict)
        assert len(dims) >= 1
        for v in dims.values():
            assert 0.0 <= v <= 1.0


# ---------------------------------------------------------------------------
# Integration tests for leaderboard generation
# ---------------------------------------------------------------------------


class TestGenerateLeaderboard:
    def test_produces_markdown(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results)
        assert "# " in md
        assert "Rankings" in md
        assert "Per-Scenario" in md

    def test_has_ranking_table(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results)
        assert "| Rank |" in md
        assert "orchestrator" in md
        assert "test-adapter-b" in md

    def test_has_dimension_heatmap(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results)
        assert "Dimension Heatmap" in md

    def test_has_containment_summary(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results)
        assert "Containment" in md

    def test_has_key_insights(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results)
        assert "Key Insights" in md

    def test_custom_title(self) -> None:
        results = _make_results()
        md = generate_leaderboard(results, title="Custom Title")
        assert "Custom Title" in md

    def test_single_result(self) -> None:
        results = _make_results()[:1]
        md = generate_leaderboard(results)
        assert "Rankings" in md


class TestWriteLeaderboard:
    def test_writes_file(self) -> None:
        results = _make_results()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "test_leaderboard.md"
            write_leaderboard(results, output)
            assert output.exists()
            content = output.read_text(encoding="utf-8")
            assert "Rankings" in content

    def test_creates_parent_dirs(self) -> None:
        results = _make_results()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sub" / "dir" / "lb.md"
            write_leaderboard(results, output)
            assert output.exists()


# ---------------------------------------------------------------------------
# CLI leaderboard command
# ---------------------------------------------------------------------------


class TestCLILeaderboard:
    def test_leaderboard_subparser_exists(self) -> None:
        """Verify the leaderboard subcommand is registered."""
        import sys
        from io import StringIO

        from agentbench.cli import main

        old_argv = sys.argv
        old_stderr = sys.stderr
        try:
            sys.argv = ["agentbench", "leaderboard", "--help"]
            sys.stderr = StringIO()
            main()
        except SystemExit as e:
            assert e.code == 0  # --help exits with 0
        finally:
            sys.argv = old_argv
            sys.stderr = old_stderr

    def test_leaderboard_missing_dir(self) -> None:
        """Non-existent traces dir should return exit code 1."""
        import argparse

        from agentbench.cli import _cmd_leaderboard

        args = argparse.Namespace(
            traces_dir=Path("/nonexistent/dir"),
            output=Path("out.md"),
            radar=False,
        )
        assert _cmd_leaderboard(args) == 1

    def test_leaderboard_empty_dir(self) -> None:
        """Empty traces dir should return exit code 1."""
        import argparse

        from agentbench.cli import _cmd_leaderboard

        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                traces_dir=Path(tmp),
                output=Path(tmp) / "out.md",
                radar=False,
            )
            assert _cmd_leaderboard(args) == 1

    def test_leaderboard_from_baselines(self) -> None:
        """Full integration: generate leaderboard from baseline traces."""
        import argparse

        from agentbench.cli import _cmd_leaderboard

        baselines = Path(__file__).parent.parent / "results" / "baseline"
        if not baselines.exists() or not list(baselines.glob("*.jsonl")):
            return  # skip if no baselines

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "LEADERBOARD.md"
            args = argparse.Namespace(
                traces_dir=baselines,
                output=output,
                radar=False,
            )
            rc = _cmd_leaderboard(args)
            assert rc == 0
            assert output.exists()
            content = output.read_text(encoding="utf-8")
            assert "Rankings" in content
            assert "orchestrator" in content


# ---------------------------------------------------------------------------
# Multi-adapter comparison (generator extension)
# ---------------------------------------------------------------------------


class TestMultiAdapterComparison:
    def test_generates_comparison(self) -> None:
        from agentbench.report.generator import generate_multi_adapter_comparison

        results = _make_results()
        md = generate_multi_adapter_comparison(results)
        assert "Cross-Adapter" in md or "Adapter" in md
        assert "orchestrator" in md
        assert "test-adapter-b" in md

    def test_includes_confusion_matrix(self) -> None:
        from agentbench.report.generator import generate_multi_adapter_comparison

        results = _make_results()
        md = generate_multi_adapter_comparison(results)
        assert "Predicted" in md or "TP=" in md or "Confusion" in md
