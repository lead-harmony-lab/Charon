"""
charon/db/repositories/route.py
System Version: v0.6.0 | File Revision: 6.1.1

Module: Data Access Layer repository for route mappings, system fallback definitions,
action trigger resolution, and dynamic shortcut override rules.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Route")


class RouteRepository:
    """Data access layer for route registries, action dispatching, and dynamic shortcut rules."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """
        Initializes the route_registry and dynamic_routing_rules database tables.

        Note: Table creation is provided here for bootstrap initialization. Once the database schema
        stabilizes, DDL logic should be executed strictly through a dedicated system migration runner.
        """
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS system_roles (
                    role_name TEXT PRIMARY KEY,
                    description TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS route_registry (
                    route_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_trigger TEXT UNIQUE NOT NULL,
                    target_role TEXT NOT NULL,
                    fallback_role TEXT DEFAULT 'system_fallback',
                    route_type TEXT CHECK(route_type IN('SYSTEM', 'USER_OVERRIDE', 'DYNAMIC_AUTO', 'EPHEMERAL')) NOT NULL DEFAULT 'DYNAMIC_AUTO',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    created_by TEXT DEFAULT 'system',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    execution_count INTEGER DEFAULT 0,
                    last_executed_at TEXT,
                    FOREIGN KEY(target_role) REFERENCES system_roles(role_name) ON DELETE RESTRICT,
                    FOREIGN KEY(fallback_role) REFERENCES system_roles(role_name) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS dynamic_routing_rules (
                    rule_id TEXT PRIMARY KEY,
                    trigger TEXT UNIQUE NOT NULL,
                    target_agent TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_route_trigger ON route_registry(action_trigger);
                CREATE INDEX IF NOT EXISTS idx_route_type ON route_registry(route_type);
                CREATE INDEX IF NOT EXISTS idx_route_active ON route_registry(is_active);
                CREATE INDEX IF NOT EXISTS idx_dynamic_rule_trigger ON dynamic_routing_rules(trigger);
            """)

            # Ensure system_fallback default role is registered in system_roles
            conn.execute(
                "INSERT OR IGNORE INTO system_roles (role_name, description) VALUES ('system_fallback', 'Default system fallback role');"
            )

    def get_system_fallback(self) -> str:
        """Returns the fallback role mapped in the system."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT target_role FROM route_registry WHERE target_role = 'system_fallback' LIMIT 1;"
            )
            row = cursor.fetchone()
            return str(row["target_role"]) if row else "system_fallback"

    def resolve_and_track_route(self, action_trigger: str) -> Optional[Tuple[str, str]]:
        """Fetches highest priority active route and increments execution telemetry."""
        with get_connection(self.db_path, row_factory=True) as conn:
            cursor = conn.execute(
                """
                SELECT target_role, fallback_role 
                FROM route_registry 
                WHERE action_trigger = ? AND is_active = 1
                ORDER BY CASE route_type
                    WHEN 'USER_OVERRIDE' THEN 1
                    WHEN 'SYSTEM' THEN 2
                    WHEN 'DYNAMIC_AUTO' THEN 3
                    WHEN 'EPHEMERAL' THEN 4
                    ELSE 5
                END ASC LIMIT 1;
                """,
                (action_trigger,),
            )
            row = cursor.fetchone()

            if row:
                conn.execute(
                    """
                    UPDATE route_registry 
                    SET execution_count = execution_count + 1, last_executed_at = CURRENT_TIMESTAMP
                    WHERE action_trigger = ?;
                    """,
                    (action_trigger,),
                )
                return str(row["target_role"]), str(row["fallback_role"])
            return None

    def get_route_type(self, action_trigger: str) -> Optional[str]:
        """Retrieves route_type classification for a given action trigger."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT route_type FROM route_registry WHERE action_trigger = ?;",
                (action_trigger,),
            )
            row = cursor.fetchone()
            return str(row["route_type"]) if row else None

    def set_route_active_status(self, action_trigger: str, is_active: bool) -> bool:
        """Operational Control: Quarantines/Disables or re-enables a route path."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE route_registry SET is_active = ? WHERE action_trigger = ?;",
                (1 if is_active else 0, action_trigger),
            )
            return cursor.rowcount > 0

    def upsert_route(
        self,
        action_trigger: str,
        target_role: str,
        fallback_role: Optional[str],
        route_type: str,
        description: str,
        created_by: str,
        force: bool = False,
    ) -> None:
        """
        Upserts a route. Throws PermissionError if attempting to mutate
        a SYSTEM route without force=True.
        """
        existing_type = self.get_route_type(action_trigger)
        if existing_type == "SYSTEM" and not force:
            raise PermissionError(
                f"Cannot mutate immutable SYSTEM route for trigger '{action_trigger}' without force flag."
            )

        with get_connection(self.db_path) as conn:
            # Seed referenced roles if they don't exist yet in system_roles
            roles_to_ensure = [r for r in (target_role, fallback_role) if r]
            for role in roles_to_ensure:
                conn.execute(
                    "INSERT OR IGNORE INTO system_roles (role_name, description) VALUES (?, ?);",
                    (role, f"Role for {role}"),
                )

            conn.execute(
                """
                INSERT INTO route_registry 
                (action_trigger, target_role, fallback_role, route_type, description, created_by, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(action_trigger) DO UPDATE SET
                    target_role = excluded.target_role,
                    fallback_role = excluded.fallback_role,
                    route_type = excluded.route_type,
                    description = excluded.description,
                    created_by = excluded.created_by,
                    is_active = 1;
                """,
                (
                    action_trigger,
                    target_role,
                    fallback_role,
                    route_type,
                    description,
                    created_by,
                ),
            )

    def sync_dynamic_routes(self) -> bool:
        """
        Synchronizes active skills from skill_registry and agent_skill_map into route_registry.
        Automatically updates or creates DYNAMIC_AUTO route entries for registered actions.
        """
        query = """
            INSERT INTO route_registry (
                action_trigger, target_role, fallback_role, route_type, description, created_by, is_active
            )
            SELECT 
                sr.action_name AS action_trigger,
                COALESCE(asm.agent_id, 'system_fallback') AS target_role,
                'system_fallback' AS fallback_role,
                'DYNAMIC_AUTO' AS route_type,
                sr.description,
                'indexer' AS created_by,
                1 AS is_active
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.status = 'ACTIVE'
            ON CONFLICT(action_trigger) DO UPDATE SET
                target_role = EXCLUDED.target_role,
                description = EXCLUDED.description,
                is_active = 1
            WHERE route_registry.route_type = 'DYNAMIC_AUTO';
        """
        try:
            with get_connection(self.db_path) as conn:
                # 1. Ensure fallback role exists in system_roles
                conn.execute(
                    "INSERT OR IGNORE INTO system_roles (role_name, description) VALUES ('system_fallback', 'Default system fallback role');"
                )

                # 2. Pre-seed system_roles with all agent_ids currently in agent_skill_map
                conn.execute(
                    """
                    INSERT OR IGNORE INTO system_roles (role_name, description)
                    SELECT DISTINCT agent_id, 'Dynamic agent execution role'
                    FROM agent_skill_map
                    WHERE agent_id IS NOT NULL AND agent_id != '*';
                    """
                )

                # 3. Synchronize routes into route_registry
                conn.execute(query)

            logger.info("[RouteRepository] Successfully synchronized dynamic routes from skill registry.")
            return True
        except Exception as e:
            logger.error(f"[RouteRepository] Failed to sync dynamic routes: {e}", exc_info=True)
            return False

    # =========================================================================
    # Dynamic Shortcut Override Rules (Pass 1 Router Support)
    # =========================================================================

    def get_override_rules(self) -> List[Dict[str, Any]]:
        """Retrieves all active dynamic hard shortcut override rules from SQLite."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT rule_id, trigger, target_agent, description, created_at FROM dynamic_routing_rules;"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def add_override_rule(self, trigger: str, target_agent: str, description: str = "") -> str:
        """
        Creates or updates a hard trigger shortcut rule (e.g. '#archivist' -> forced dispatch).
        Returns the rule_id assigned to the shortcut.
        """
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO dynamic_routing_rules (rule_id, trigger, target_agent, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trigger) DO UPDATE SET
                    target_agent = excluded.target_agent,
                    description = excluded.description;
                """,
                (rule_id, trigger.strip(), target_agent.strip(), description),
            )

        logger.info(f"[RouteRepository] Added dynamic shortcut rule '{trigger}' -> '{target_agent}' ({rule_id}).")
        return rule_id

    def remove_override_rule(self, rule_id: str) -> bool:
        """Deletes a dynamic shortcut rule by rule_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM dynamic_routing_rules WHERE rule_id = ?;", (rule_id,))
            removed = cursor.rowcount > 0

        if removed:
            logger.info(f"[RouteRepository] Removed shortcut rule '{rule_id}'.")
            return removed