"""
charon/core/dispatcher/router_tool.py
System Version: v0.4.0 | File Revision: 2.3.0

Module: Visualization and tuning tool for the routing engine.
Provides CLI-friendly utilities for monitoring, overriding, and quarantining dispatch routes.
Updated to strictly align with SQLite schema column definitions (action_trigger, target_role).
"""

import sqlite3
from pathlib import Path
from typing import Union

from charon.core.dispatcher.router import AgentRouter
from charon.core.skills.librarian import SkillLibrarian
from charon.db.connection import get_connection


class RouterManagerTool:
    """Admin tool for visualizing, editing, and quarantining dispatcher routes."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.router = AgentRouter(self.db_path)

    def render_route_table_ascii(self) -> str:
        """Renders an ASCII visualization table of all registered routes."""
        if not self.db_path.exists():
            return "Database not initialized."

        try:
            with get_connection(self.db_path, read_only=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT action_trigger, target_role, fallback_role, route_type, is_active, execution_count, created_by
                    FROM route_registry
                    ORDER BY route_type ASC, action_trigger ASC;
                """)
                rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            return f"Database query failed on 'route_registry': {e}"

        if not rows:
            return "No routes registered in route_registry."

        header = f"{'ACTION TRIGGER':<28} | {'TARGET ROLE':<20} | {'FALLBACK ROLE':<18} | {'TYPE':<14} | {'STATUS':<8} | {'CALLS':<6} | {'OWNER':<12}"
        divider = "-" * len(header)
        lines = [header, divider]

        for row in rows:
            action = row["action_trigger"]
            role = row["target_role"]
            fallback = row["fallback_role"]
            rtype = row["route_type"]
            active = row["is_active"]
            calls = row["execution_count"]
            owner = row["created_by"]

            status = "ACTIVE" if active else "DISABLED"
            action_str = str(action)[:28] if action else "UNKNOWN"
            role_str = str(role)[:20] if role else "UNASSIGNED"
            fallback_str = str(fallback)[:18] if fallback else "NONE"
            rtype_str = str(rtype)[:14] if rtype else "DEFAULT"
            owner_str = str(owner)[:12] if owner else "SYSTEM"
            calls_str = str(calls) if calls is not None else "0"

            lines.append(
                f"{action_str:<28} | {role_str:<20} | {fallback_str:<18} | {rtype_str:<14} | {status:<8} | {calls_str:<6} | {owner_str:<12}"
            )

        return "\n".join(lines)

    def set_route_override(
        self, action_trigger: str, target_role: str, description: str = ""
    ) -> str:
        """Sets a high-priority USER_OVERRIDE on an action trigger."""
        try:
            self.router.register_route(
                action_trigger=action_trigger,
                target_role=target_role,
                route_type="USER_OVERRIDE",
                description=description,
                created_by="operator_cli",
                force=True,
            )
            librarian = SkillLibrarian.get_instance(self.db_path)
            canonical_target = librarian.resolve_agent_id_for_role(target_role) or target_role
            return f"Successfully applied USER_OVERRIDE for '{action_trigger}' -> '{canonical_target}'"
        except Exception as e:
            return f"Failed to set route override: {e}"

    def set_route_status(self, action_trigger: str, is_active: bool) -> str:
        """Quarantines or re-enables a route by action_trigger without deleting it."""
        if not self.db_path.exists():
            return "Failed to set status: Database not found."

        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE route_registry SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE action_trigger = ?",
                    (1 if is_active else 0, action_trigger),
                )
                affected = cursor.rowcount
        except sqlite3.OperationalError as e:
            return f"Database error while updating route status: {e}"

        # Invalidate cache so the router picks up the quarantined status immediately
        self.router.clear_cache()

        if affected > 0:
            status_str = "ENABLED" if is_active else "QUARANTINED"
            return f"Route '{action_trigger}' is now {status_str}."
        return f"Route '{action_trigger}' not found."

    def delete_route(self, action_trigger: str) -> str:
        """Deletes a custom dynamic or override route from route_registry."""
        if not self.db_path.exists():
            return "Failed to delete route: Database not found."

        try:
            with get_connection(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT route_type FROM route_registry WHERE action_trigger = ?", (action_trigger,))
                row = cursor.fetchone()

                if not row:
                    return f"Route '{action_trigger}' not found."

                if row["route_type"] == "SYSTEM":
                    return f"Cannot delete SYSTEM route '{action_trigger}'. Use quarantining (set_route_status) instead."

                cursor.execute("DELETE FROM route_registry WHERE action_trigger = ?", (action_trigger,))
        except sqlite3.OperationalError as e:
            return f"Database error while deleting route: {e}"

        self.router.clear_cache()
        return f"Successfully deleted route for '{action_trigger}'."