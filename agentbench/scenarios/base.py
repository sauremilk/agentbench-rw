"""Base scenario class with lifecycle: setup → inject → run → verify → teardown."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentbench.types import (
    AgentAction,
    AgentTrace,
    EscalationLabel,
    ScenarioConfig,
    SecurityZone,
    TargetAdapter,
)


@dataclass
class VerificationResult:
    """Outcome of scenario verification against ground truth."""

    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class BaseScenario(ABC):
    """Abstract base for all evaluation scenarios.

    Lifecycle:
        1. ``setup(adapter)``   — prepare adapter and inject scenario state
        2. ``get_actions()``    — return the action sequence the agent should attempt
        3. ``verify(trace)``    — check results against ground truth
        4. ``teardown()``       — clean up
    """

    @property
    @abstractmethod
    def config(self) -> ScenarioConfig:
        """Return the scenario configuration (name, labels, expected files, etc.)."""

    def setup(self, adapter: TargetAdapter) -> None:
        """Set up the adapter for this scenario (calls adapter.setup_scenario)."""
        adapter.setup_scenario(self.config)

    @abstractmethod
    def get_actions(self) -> list[AgentAction]:
        """Return the ordered sequence of agent actions for this scenario."""

    @abstractmethod
    def verify(self, trace: AgentTrace) -> VerificationResult:
        """Verify trace against ground-truth expectations."""

    def teardown(self) -> None:  # noqa: B027
        """Clean up after scenario execution (override if needed)."""


# ---------------------------------------------------------------------------
# Helpers for building scenario configs
# ---------------------------------------------------------------------------


def make_config(
    name: str,
    *,
    description: str = "",
    adapter_name: str = "",
    expected_files: list[str] | None = None,
    ground_truth: dict[str, EscalationLabel] | None = None,
    inject: dict[str, object] | None = None,
    timeout: float = 300.0,
) -> ScenarioConfig:
    """Convenience builder for ScenarioConfig."""
    return ScenarioConfig(
        name=name,
        description=description,
        adapter_name=adapter_name,
        expected_files=expected_files or [],
        ground_truth_labels=ground_truth or {},
        inject_data=inject or {},
        timeout_seconds=timeout,
    )


def expected_zone_sequence(
    actions: list[AgentAction],
    zone_map: dict[str, SecurityZone],
) -> list[SecurityZone]:
    """Compute expected security zones for a sequence of actions using a zone map."""
    from agentbench.adapters.base import _match_zone

    zones: list[SecurityZone] = []
    for action in actions:
        if action.file_path:
            zones.append(_match_zone(action.file_path, zone_map))
        else:
            zones.append(SecurityZone.NORMAL)
    return zones
