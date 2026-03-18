"""Base adapter utilities — helpers for implementing TargetAdapter."""

from __future__ import annotations

from agentbench.types import (
    AgentAction,
    AgentTrace,
    ScenarioConfig,
    SecurityZone,
    Turn,
    TurnResult,
)


class BaseAdapter:
    """Convenience base class implementing shared adapter logic.

    Subclasses must implement:
    - ``_do_execute(action) -> TurnResult`` — the actual agent call
    - ``_zone_map`` — a dict mapping path prefixes to SecurityZone

    Provides:
    - Automatic trace recording (turns + events)
    - Security zone lookup by path prefix
    """

    _zone_map: dict[str, SecurityZone] = {}

    def __init__(self) -> None:
        self._turns: list[Turn] = []
        self._scenario: ScenarioConfig | None = None
        self._metadata: dict[str, object] = {}

    # --- TargetAdapter Protocol methods ---

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def setup_scenario(self, scenario: ScenarioConfig) -> None:
        self._scenario = scenario
        self._turns = []
        self._metadata = {}

    def execute_turn(self, action: AgentAction) -> TurnResult:
        result = self._do_execute(action)
        turn = Turn(
            turn_number=len(self._turns) + 1,
            duration_ms=result.duration_ms,
            tokens_input=result.tokens_used,  # total from TurnResult
            tool_calls=result.tool_calls,
            events=result.events,
        )
        self._turns.append(turn)
        return result

    def get_security_zone(self, file_path: str) -> SecurityZone:
        return _match_zone(file_path, self._zone_map)

    def check_escalation_needed(self, file_path: str) -> bool:
        zone = self.get_security_zone(file_path)
        return zone in (SecurityZone.CRITICAL, SecurityZone.SENSITIVE)

    def teardown(self) -> None:
        pass

    def get_trace(self) -> AgentTrace:
        return AgentTrace(
            adapter_name=self.name,
            scenario_name=self._scenario.name if self._scenario else "unknown",
            turns=list(self._turns),
            metadata=dict(self._metadata),
        )

    # --- Abstract method for subclasses ---

    def _do_execute(self, action: AgentAction) -> TurnResult:
        msg = "Subclasses must implement _do_execute"
        raise NotImplementedError(msg)


def _match_zone(
    file_path: str,
    zone_map: dict[str, SecurityZone],
) -> SecurityZone:
    """Match file path against zone map using longest-prefix matching."""
    normalized = file_path.replace("\\", "/")
    best_match = SecurityZone.NORMAL
    best_length = 0

    for prefix, zone in zone_map.items():
        prefix_normalized = prefix.replace("\\", "/")
        if normalized.startswith(prefix_normalized) and len(prefix_normalized) > best_length:
            best_match = zone
            best_length = len(prefix_normalized)

    return best_match


def build_zone_map(
    critical: list[str] | None = None,
    sensitive: list[str] | None = None,
) -> dict[str, SecurityZone]:
    """Helper to build a zone map from path prefix lists."""
    zone_map: dict[str, SecurityZone] = {}
    for path in critical or []:
        zone_map[path] = SecurityZone.CRITICAL
    for path in sensitive or []:
        zone_map[path] = SecurityZone.SENSITIVE
    return zone_map
