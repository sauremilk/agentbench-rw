"""Security zone map — generic orchestrator security zone definitions.

Zones: 🔴 CRITICAL | 🟡 SENSITIVE | 🟢 NORMAL

🔴 CRITICAL — User approval required (no autonomous changes)
🟡 SENSITIVE — Peer review + policy compliance check required
🟢 NORMAL   — Standard autonomous workflow
"""

from agentbench.adapters.base import build_zone_map
from agentbench.types import SecurityZone

# ---------------------------------------------------------------------------
# Path prefixes per zone
# ---------------------------------------------------------------------------

CRITICAL_PATHS: list[str] = [
    "auth/",
    "auth.py",
    "migrations/",
    ".env",
    "secrets/",
    "db/migrations/",
    "models/user.py",
]

SENSITIVE_PATHS: list[str] = [
    "policies/",
    "config/",
    "middleware/",
    "integrations/",
]


def get_orchestrator_zone_map() -> dict[str, SecurityZone]:
    """Build the orchestrator zone map from security zone definitions."""
    return build_zone_map(critical=CRITICAL_PATHS, sensitive=SENSITIVE_PATHS)


# Pre-built for direct import
ORCHESTRATOR_ZONE_MAP: dict[str, SecurityZone] = get_orchestrator_zone_map()
