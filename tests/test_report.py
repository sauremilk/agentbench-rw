"""Tests for report generation (Markdown + SVG radar)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agentbench.report.generator import generate_markdown_report, generate_report_with_radar
from agentbench.report.radar import render_radar_svg
from agentbench.scoring import compute_score
from agentbench.types import AgentTrace, Turn


def _make_simple_result():
    """Build a minimal EvalResult for testing."""
    trace = AgentTrace(adapter_name="report-test", scenario_name="s1")
    trace.turns.append(
        Turn(
            turn_number=1,
            start_time="t0",
            end_time="t1",
            duration_ms=200.0,
            tokens_input=800,
            tokens_output=300,
        )
    )
    trace.success = True
    from agentbench.scoring import ScoringInput

    metrics = ScoringInput(
        tasks_attempted=1,
        tasks_succeeded=1,
        turn_latencies_ms=[200.0],
        total_tokens=1100,
        total_actions=3,
        autonomy_eligible=1,
        autonomy_completed=1,
    )
    return compute_score(trace, metrics)


class TestRadarSVG:
    def test_produces_valid_svg(self):
        scores = {
            "task_completion": 0.9,
            "latency": 0.8,
            "cost_efficiency": 0.7,
            "safety_compliance": 1.0,
            "containment": 0.6,
            "reliability": 0.85,
            "autonomy": 0.5,
        }
        svg = render_radar_svg(scores)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_includes_all_labels(self):
        scores = {f"dim_{i}": 0.5 for i in range(7)}
        svg = render_radar_svg(scores)
        assert "<text" in svg

    def test_custom_color(self):
        scores = {"a": 0.5, "b": 0.5, "c": 0.5}
        svg = render_radar_svg(scores, color="#ff0000")
        assert "#ff0000" in svg


class TestMarkdownReport:
    def test_contains_header(self):
        result = _make_simple_result()
        md = generate_markdown_report(result)
        assert "# AgentBench-RW" in md
        assert "report-test" in md
        assert "s1" in md

    def test_contains_dimension_table(self):
        result = _make_simple_result()
        md = generate_markdown_report(result)
        assert "| Dimension" in md
        assert "Completion" in md or "completion" in md.lower()

    def test_contains_composite_score(self):
        result = _make_simple_result()
        md = generate_markdown_report(result)
        assert "Composite Score" in md
        assert "/ 100" in md

    def test_grade_is_present(self):
        result = _make_simple_result()
        md = generate_markdown_report(result)
        assert any(grade in md for grade in ["A", "B", "C", "D", "F"])


class TestReportWithRadar:
    def test_writes_both_files(self):
        result = _make_simple_result()
        with tempfile.TemporaryDirectory() as tmp:
            md_path, svg_path = generate_report_with_radar(result, Path(tmp))
            assert md_path.exists()
            assert svg_path.exists()
            assert md_path.suffix == ".md"
            assert svg_path.suffix == ".svg"
