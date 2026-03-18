"""Reliability instrument — failure classification and recovery tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbench.types import FailureBreakdown, FailureCategory, FailureCode, TraceEvent

# Map failure codes → categories
_CODE_TO_CATEGORY: dict[str, FailureCategory] = {
    "IF-001": FailureCategory.INFRASTRUCTURE,
    "IF-002": FailureCategory.INFRASTRUCTURE,
    "IF-003": FailureCategory.INFRASTRUCTURE,
    "IF-004": FailureCategory.INFRASTRUCTURE,
    "PF-001": FailureCategory.PLANNER,
    "PF-002": FailureCategory.PLANNER,
    "PF-003": FailureCategory.PLANNER,
    "PF-004": FailureCategory.PLANNER,
    "PF-005": FailureCategory.PLANNER,
    "TF-001": FailureCategory.TOOL,
    "TF-002": FailureCategory.TOOL,
    "TF-003": FailureCategory.TOOL,
    "TF-004": FailureCategory.TOOL,
    "SV-001": FailureCategory.SAFETY_VIOLATION,
    "SV-002": FailureCategory.SAFETY_VIOLATION,
    "SV-003": FailureCategory.SAFETY_VIOLATION,
    "SV-004": FailureCategory.SAFETY_VIOLATION,
    "RP-001": FailureCategory.RECOVERY,
    "RP-002": FailureCategory.RECOVERY,
    "RP-003": FailureCategory.RECOVERY,
    "RP-004": FailureCategory.RECOVERY,
}


@dataclass
class ReliabilityTracker:
    """Classifies failures by category and tracks recovery patterns.

    Usage:
        tracker = ReliabilityTracker()
        tracker.record_failure(FailureCode.IF_001)
        tracker.record_failure(FailureCode.RP_001)  # recovery
        breakdown = tracker.breakdown
        print(breakdown.recovery_rate)  # 1.0
    """

    _counts: dict[FailureCategory, int] = field(default_factory=lambda: {c: 0 for c in FailureCategory})

    def record_failure(self, code: FailureCode) -> FailureCategory:
        """Record a failure event by its code. Returns the mapped category."""
        category = _CODE_TO_CATEGORY.get(code.value, FailureCategory.TOOL)
        self._counts[category] += 1
        return category

    def record_from_event(self, event: TraceEvent) -> FailureCategory | None:
        """Record from a trace event if it has a failure code."""
        if event.failure_code is not None:
            return self.record_failure(event.failure_code)
        return None

    def record_events(self, events: list[TraceEvent]) -> int:
        """Record all events that have failure codes. Returns count recorded."""
        return sum(1 for e in events if self.record_from_event(e) is not None)

    @property
    def breakdown(self) -> FailureBreakdown:
        return FailureBreakdown(
            infrastructure=self._counts[FailureCategory.INFRASTRUCTURE],
            planner=self._counts[FailureCategory.PLANNER],
            tool=self._counts[FailureCategory.TOOL],
            safety_violation=self._counts[FailureCategory.SAFETY_VIOLATION],
            recovery_success=self._counts[FailureCategory.RECOVERY],
        )

    @property
    def composite_reliability(self) -> float:
        """R = 1 - (unrecovered_failures / total_actions).

        Note: total_actions must be set by caller. This returns unrecovered failure count.
        """
        b = self.breakdown
        return float(b.total_failures - b.recovery_success)

    def reset(self) -> None:
        for cat in FailureCategory:
            self._counts[cat] = 0
