"""TAU2-Bench adapter — replay-only adapter for Sierra TAU-Bench conversations.

Unlike the Orchestrator/LangGraph/AutoGen adapters, TAU2-Bench is a
*replay-only* adapter: it loads pre-recorded conversations and converts
them into AgentBench traces for re-scoring with the 7-dimension engine.

This adapter never makes live LLM calls.
"""

from __future__ import annotations

import time
from typing import Any

from agentbench.adapters.base import BaseAdapter, build_zone_map
from agentbench.adapters.tau2bench.converter import convert_tau2_conversation
from agentbench.types import AgentAction, TurnResult

# ---------------------------------------------------------------------------
# Zone maps for TAU2 customer-service domains
# ---------------------------------------------------------------------------

_CRITICAL_PATHS = [
    "payment/",
    "refund/",
    "credit_card/",
    "account_deletion/",
]

_SENSITIVE_PATHS = [
    "booking/",
    "customer_data/",
    "personal_info/",
    "order/",
]


class TAU2BenchAdapter(BaseAdapter):
    """Replay-only adapter for TAU2-Bench customer-service conversations.

    The adapter loads embedded or file-provided TAU2-format conversation
    data and replays it turn-by-turn.  Each ``_do_execute()`` call returns
    the next pre-recorded turn.

    Supported action types:
    - ``replay_turn``  — replay the next conversation turn
    - ``load``         — inject conversation data for future turns

    Zone mapping: tool names in TAU2 conversations are mapped to
    security zones via the optional ``tool_zone_map`` on the scenario.
    """

    _zone_map = build_zone_map(critical=_CRITICAL_PATHS, sensitive=_SENSITIVE_PATHS)

    # Action types this adapter processes
    ACTION_TYPES = ("replay_turn", "load")

    def __init__(self) -> None:
        super().__init__()
        self._conversation_data: dict[str, Any] | None = None
        self._tool_zone_map: dict[str, str] | None = None
        self._replay_turns: list[Any] = []
        self._replay_index: int = 0

    @property
    def name(self) -> str:
        return "tau2bench"

    def setup_scenario(self, scenario: Any) -> None:
        super().setup_scenario(scenario)
        self._replay_index = 0
        self._replay_turns = []

        # Scenario can inject conversation data
        if self._scenario and self._scenario.inject_data:
            inject = self._scenario.inject_data
            self._conversation_data = inject.get("conversation", None)
            self._tool_zone_map = inject.get("tool_zone_map", None)
            if self._conversation_data:
                self._build_replay_turns()

    def _build_replay_turns(self) -> None:
        """Pre-convert conversation data into an AgentTrace for replay."""
        if not self._conversation_data:
            return
        trace = convert_tau2_conversation(
            self._conversation_data,
            zone_map=self._tool_zone_map,
        )
        self._replay_turns = list(trace.turns)

    # -----------------------------------------------------------------------
    # Core execution — replay mode
    # -----------------------------------------------------------------------

    def _do_execute(self, action: AgentAction) -> TurnResult:
        t0 = time.perf_counter()

        handler = self._ACTION_HANDLERS.get(action.action_type, self._handle_replay_turn)
        result = handler(self, action)

        elapsed = (time.perf_counter() - t0) * 1000
        result.duration_ms = elapsed
        return result

    # -----------------------------------------------------------------------
    # Action handlers
    # -----------------------------------------------------------------------

    def _handle_replay_turn(self, action: AgentAction) -> TurnResult:
        """Replay the next pre-recorded turn from the conversation."""
        if self._replay_index >= len(self._replay_turns):
            return TurnResult(
                success=True,
                events=[],
            )

        turn = self._replay_turns[self._replay_index]
        self._replay_index += 1

        return TurnResult(
            success=True,
            events=list(turn.events),
            tool_calls=list(turn.tool_calls),
        )

    def _handle_load(self, action: AgentAction) -> TurnResult:
        """Load conversation data from action arguments."""
        conv = action.arguments.get("conversation")
        if conv and isinstance(conv, dict):
            self._conversation_data = conv
            self._tool_zone_map = action.arguments.get("tool_zone_map")
            self._build_replay_turns()
            return TurnResult(
                success=True,
                events=[],
            )
        return TurnResult(
            success=False,
            events=[],
            error="Missing or invalid 'conversation' in action arguments",
        )

    # -----------------------------------------------------------------------
    # Handler dispatch table
    # -----------------------------------------------------------------------

    _ACTION_HANDLERS: dict[str, Any] = {
        "replay_turn": _handle_replay_turn,
        "load": _handle_load,
    }
