"""
charon/core/skills/routes.py
System Version: v0.6.0 | File Revision: 6.0.0

Route lifecycle, provenance resolution, and operational telemetry tracking mixin for SkillLibrarian.
Enforces CBAC Schema V2 routing constraints and quarantine state filtering.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Core.Skills.Routes")


class RouteManagerMixin:
    """Route Provenance and Telemetry management for SkillLibrarian."""

    def resolve_route(self, action_or_route: str) -> Optional[Dict[str, Any]]:
        """
        Queries RouteRepository for route provenance and operational status.
        Precedence: USER_OVERRIDE > SYSTEM > DYNAMIC_AUTO > FALLBACK
        Filters out quarantined or inactive routes.
        """
        if not action_or_route:
            return None

        clean_trigger = action_or_route.strip().lower()

        try:
            if hasattr(self, "route_repo") and hasattr(self.route_repo, "get_route"):
                route = self.route_repo.get_route(clean_trigger)
                if route and route.get("is_active", True):
                    status = str(route.get("status", "ACTIVE")).upper()
                    if status == "ACTIVE":
                        return route
        except Exception as e:
            logger.error(
                f"[LIBRARIAN] Error resolving route '{action_or_route}': {e}"
            )
        return None

    def record_route_execution(self, route_id: str) -> None:
        """Updates route operational telemetry (execution_count & last_executed_at)."""
        if not route_id:
            return

        try:
            if hasattr(self, "route_repo") and hasattr(self.route_repo, "record_execution"):
                self.route_repo.record_execution(route_id)
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Telemetry update failed for route '{route_id}': {e}"
            )