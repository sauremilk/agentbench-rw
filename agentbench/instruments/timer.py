"""Timer instrument — perf_counter wrapper with percentile statistics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agentbench.types import LatencyStats


@dataclass
class Timer:
    """Collects timing measurements and computes percentile statistics.

    Usage:
        timer = Timer()
        with timer.measure():
            do_something()
        stats = timer.stats()
    """

    _measurements: list[float] = field(default_factory=list, repr=False)

    def measure(self) -> _TimerContext:
        """Context manager that records elapsed wall-clock time in ms."""
        return _TimerContext(self._measurements)

    def record(self, duration_ms: float) -> None:
        """Manually record a duration measurement."""
        self._measurements.append(duration_ms)

    def stats(self) -> LatencyStats:
        """Compute percentile statistics over all recorded measurements."""
        if not self._measurements:
            return LatencyStats()

        sorted_ms = sorted(self._measurements)
        n = len(sorted_ms)

        return LatencyStats(
            p50_ms=_percentile(sorted_ms, 50, n),
            p95_ms=_percentile(sorted_ms, 95, n),
            p99_ms=_percentile(sorted_ms, 99, n),
            mean_ms=sum(sorted_ms) / n,
            count=n,
        )

    def reset(self) -> None:
        self._measurements.clear()


class _TimerContext:
    """Context manager for Timer.measure()."""

    __slots__ = ("_measurements", "_start")

    def __init__(self, measurements: list[float]) -> None:
        self._measurements = measurements
        self._start: float = 0.0

    def __enter__(self) -> _TimerContext:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self._measurements.append(elapsed_ms)

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000 if self._start else 0.0


def _percentile(sorted_values: list[float], pct: int, n: int) -> float:
    """Compute percentile from pre-sorted values (nearest-rank method)."""
    if n == 0:
        return 0.0
    idx = max(0, min(int(pct / 100 * n) - 1, n - 1))
    return sorted_values[idx]
