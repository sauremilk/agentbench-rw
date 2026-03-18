"""Scenario registry — auto-discovery and lookup of evaluation scenarios."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbench.scenarios.base import BaseScenario


class ScenarioRegistry:
    """Registry mapping scenario names to their classes.

    Usage::

        registry = ScenarioRegistry()
        registry.register("s1_bugfix", S1SoloBugfix)
        scenario = registry.get("s1_bugfix")
    """

    def __init__(self) -> None:
        self._scenarios: dict[str, type[BaseScenario]] = {}

    def register(self, name: str, cls: type[BaseScenario]) -> None:
        self._scenarios[name] = cls

    def get(self, name: str) -> BaseScenario:
        if name not in self._scenarios:
            available = ", ".join(sorted(self._scenarios)) or "(none)"
            msg = f"Unknown scenario {name!r}. Available: {available}"
            raise KeyError(msg)
        return self._scenarios[name]()

    def list_scenarios(self) -> list[str]:
        return sorted(self._scenarios)

    def __contains__(self, name: str) -> bool:
        return name in self._scenarios

    def __len__(self) -> int:
        return len(self._scenarios)


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------

_registry_singleton: ScenarioRegistry | None = None


def get_registry() -> ScenarioRegistry:
    """Return the global scenario registry, auto-discovering scenarios on first call."""
    global _registry_singleton  # noqa: PLW0603
    if _registry_singleton is None:
        _registry_singleton = ScenarioRegistry()
        _auto_discover(_registry_singleton)
    return _registry_singleton


def _auto_discover(registry: ScenarioRegistry) -> None:
    """Walk adapter scenario sub-packages and register all BaseScenario subclasses."""
    import agentbench.adapters as adapters_pkg

    for _importer, modname, ispkg in pkgutil.walk_packages(
        adapters_pkg.__path__,
        prefix="agentbench.adapters.",
    ):
        if not ispkg and "scenarios" in modname:
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            _register_from_module(registry, mod)


def _register_from_module(registry: ScenarioRegistry, mod: object) -> None:
    """Register all BaseScenario subclasses found in a module."""
    from agentbench.scenarios.base import BaseScenario

    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and issubclass(attr, BaseScenario) and attr is not BaseScenario:
            # Use the scenario config name if available, else class name
            try:
                instance = attr()
                name = instance.config.name
            except Exception:
                name = attr_name
            registry.register(name, attr)
