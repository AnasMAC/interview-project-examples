"""Geometry for the small inline-SVG charts.

Only numbers are computed here; the templates draw the shapes and print the
labels, so autoescaping applies to everything that reaches the page.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SEVERITY_ORDER = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class Bar:
    label: str
    value: int
    y: int
    width: int
    text_y: int
    value_x: int


@dataclass(frozen=True)
class BarChart:
    bars: list[Bar]
    width: int
    height: int
    label_width: int
    bar_height: int


def bar_chart(
    counts: Mapping[str, int],
    order: Sequence[str],
    *,
    width: int = 480,
    label_width: int = 80,
    bar_height: int = 22,
    gap: int = 10,
) -> BarChart:
    """Horizontal bars, one per label in ``order`` (missing labels count 0)."""
    plot_width = width - label_width - 40  # room for the value after the bar
    peak = max((counts.get(label, 0) for label in order), default=0) or 1
    bars = []
    for i, label in enumerate(order):
        value = counts.get(label, 0)
        y = i * (bar_height + gap)
        bar_width = round(plot_width * value / peak)
        bars.append(
            Bar(
                label=label,
                value=value,
                y=y,
                width=bar_width,
                text_y=y + bar_height - 6,
                value_x=label_width + bar_width + 6,
            )
        )
    height = len(order) * (bar_height + gap) - gap if order else 0
    return BarChart(bars=bars, width=width, height=height, label_width=label_width, bar_height=bar_height)
