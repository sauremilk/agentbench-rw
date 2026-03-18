"""SVG Radar chart — zero external dependencies.

Generates a 7-axis radar chart for agent evaluation dimensions.
Pure math + string templating, no matplotlib/plotly/etc.
"""

from __future__ import annotations

import math

# Dimension labels matching the 7 dimensions in scoring
_LABELS = [
    "Completion",
    "Latency",
    "Cost",
    "Safety",
    "Containment",
    "Reliability",
    "Autonomy",
]

_SVG_SIZE = 400
_CENTER = _SVG_SIZE / 2
_RADIUS = 150
_LABEL_OFFSET = 22


def _polar_to_xy(angle_deg: float, r: float) -> tuple[float, float]:
    """Convert polar coordinates to SVG x,y."""
    rad = math.radians(angle_deg - 90)  # start from top
    return _CENTER + r * math.cos(rad), _CENTER + r * math.sin(rad)


def _polygon_points(values: list[float], max_val: float = 1.0) -> str:
    """Generate SVG points string for a polygon."""
    n = len(values)
    angle_step = 360.0 / n
    points = []
    for i, v in enumerate(values):
        r = _RADIUS * min(v / max_val, 1.0) if max_val > 0 else 0
        x, y = _polar_to_xy(i * angle_step, r)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def render_radar_svg(
    scores: dict[str, float],
    *,
    title: str = "Agent Evaluation",
    color: str = "#4A90D9",
    threshold_color: str = "#E8E8E8",
    thresholds: dict[str, float] | None = None,
) -> str:
    """Render a 7-axis radar chart as SVG string.

    Args:
        scores: dimension name → normalized score (0.0 to 1.0)
        title: Chart title
        color: Fill color for the score polygon
        threshold_color: Fill color for threshold ring
        thresholds: Optional threshold values per dimension (shown as inner polygon)

    Returns:
        Complete SVG markup as string.
    """
    n = len(_LABELS)
    angle_step = 360.0 / n
    values = [scores.get(label.lower(), 0.0) for label in _LABELS]

    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_SVG_SIZE} {_SVG_SIZE}" '
        f'width="{_SVG_SIZE}" height="{_SVG_SIZE}">'
    )
    lines.append(f"<title>{title}</title>")

    # Background
    lines.append(f'<rect width="{_SVG_SIZE}" height="{_SVG_SIZE}" fill="white"/>')

    # Grid rings
    for ring in [0.25, 0.5, 0.75, 1.0]:
        r = _RADIUS * ring
        lines.append(
            f'<circle cx="{_CENTER}" cy="{_CENTER}" r="{r:.1f}" fill="none" stroke="#E0E0E0" stroke-width="0.5"/>'
        )

    # Grid spokes
    for i in range(n):
        x, y = _polar_to_xy(i * angle_step, _RADIUS)
        lines.append(
            f'<line x1="{_CENTER}" y1="{_CENTER}" x2="{x:.1f}" y2="{y:.1f}" stroke="#E0E0E0" stroke-width="0.5"/>'
        )

    # Threshold polygon (if provided)
    if thresholds:
        thresh_values = [thresholds.get(label.lower(), 0.5) for label in _LABELS]
        pts = _polygon_points(thresh_values)
        lines.append(
            f'<polygon points="{pts}" fill="{threshold_color}" '
            f'fill-opacity="0.3" stroke="{threshold_color}" '
            f'stroke-width="1" stroke-dasharray="4,4"/>'
        )

    # Score polygon
    pts = _polygon_points(values)
    lines.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.25" stroke="{color}" stroke-width="2"/>')

    # Score dots
    for i, v in enumerate(values):
        r = _RADIUS * min(v, 1.0)
        x, y = _polar_to_xy(i * angle_step, r)
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')

    # Labels
    for i, label in enumerate(_LABELS):
        x, y = _polar_to_xy(i * angle_step, _RADIUS + _LABEL_OFFSET)
        anchor = "middle"
        if x < _CENTER - 10:
            anchor = "end"
        elif x > _CENTER + 10:
            anchor = "start"

        score_val = values[i]
        lines.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-family="system-ui, sans-serif" font-size="11" fill="#333">'
            f"{label} ({score_val:.0%})</text>"
        )

    # Title
    lines.append(
        f'<text x="{_CENTER}" y="25" text-anchor="middle" '
        f'font-family="system-ui, sans-serif" font-size="14" '
        f'font-weight="bold" fill="#111">{title}</text>'
    )

    lines.append("</svg>")
    return "\n".join(lines)
