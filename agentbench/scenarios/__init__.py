"""Scenario infrastructure — base class, registry, and discovery."""

from agentbench.scenarios.base import BaseScenario
from agentbench.scenarios.registry import ScenarioRegistry, get_registry

__all__ = ["BaseScenario", "ScenarioRegistry", "get_registry"]
