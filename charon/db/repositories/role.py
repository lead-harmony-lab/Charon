"""
charon/db/repositories/role.py
System Version: v0.6.2 | File Revision: 7.0.0

Module: Data Access Layer repository for system role mappings, fallback agent selection,
agent entrypoint reflection, role criticality checks, and agent lifecycle plug/unplug execution.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Role")


class RoleRepository:
    """Data access layer for system role resolution, harness integrity, and interface abstraction."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """Initializes the system_roles table aligned with Schema V2 database constraints."""
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS system_roles (
                    role_name TEXT PRIMARY KEY,
                    agent_id TEXT,                               -- Nullable to allow agent swapping
                    is_mandatory INTEGER NOT NULL DEFAULT 0,    -- Harness requirement flag
                    is_system_core INTEGER NOT NULL DEFAULT 0,   -- Core vs custom role flag
                    description TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_system_roles_agent ON system_roles(agent_id);
            """)

    def verify_harness_boot(self) -> Tuple[bool, List[str]]:
        """Verifies that all mandatory system roles are bound to active agents."""
        query = """
            SELECT r.role_name 
            FROM system_roles r
            LEFT JOIN agent_registry a ON r.agent_id = a.agent_id
            WHERE r.is_mandatory = 1 
              AND (r.agent_id IS NULL OR a.is_active = 0);
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query)
            missing = [str(row["role_name"]) for row in cursor.fetchall()]

        if missing:
            logger.error("Harness boot check failed. Missing active agents for mandatory roles: %s", missing)
            return False, missing

        logger.info("Harness boot check passed. All mandatory system roles are active.")
        return True, []

    def swap_agent_role(self, role_name: str, new_agent_id: Optional[str]) -> bool:
        """
        Safely assigns or clears an agent for a given system role.
        """
        query = """
            UPDATE system_roles 
            SET agent_id = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE role_name = ?;
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (new_agent_id, role_name))
            updated = cursor.rowcount > 0

        if updated:
            logger.info("Successfully swapped agent for role '%s' -> '%s'", role_name, new_agent_id)
        else:
            logger.warning("Failed to swap agent for role '%s'. Role not found.", role_name)

        return updated

    def get_agent_id_for_role(self, role_input: str) -> Optional[str]:
        """
        Queries SQLite to resolve an active agent_id from:
        1. agent_registry (matching agent_id or display_name)
        2. system_roles (matching role_name -> mapped agent_id)

        Enforces active status (`is_active = 1`).
        """
        if not role_input or not str(role_input).strip():
            return None

        target = str(role_input).strip()

        query = """
            SELECT a.agent_id
            FROM agent_registry a
            WHERE (a.agent_id = ? OR LOWER(a.agent_id) = LOWER(?) OR LOWER(a.display_name) = LOWER(?))
              AND a.is_active = 1

            UNION ALL

            SELECT r.agent_id
            FROM system_roles r
            JOIN agent_registry a ON r.agent_id = a.agent_id
            WHERE (r.role_name = ? OR LOWER(r.role_name) = LOWER(?))
              AND a.is_active = 1

            LIMIT 1;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (target, target, target, target, target))
            row = cursor.fetchone()
            if row and row["agent_id"]:
                return str(row["agent_id"])

        return None

    def get_default_agent_id(self) -> Optional[str]:
        """Retrieves the system fallback agent or the first active agent."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT agent_id FROM system_roles WHERE role_name = 'system_fallback' AND agent_id IS NOT NULL LIMIT 1;"
            )
            row = cursor.fetchone()
            if row and row["agent_id"]:
                return str(row["agent_id"])

            cursor = conn.execute(
                "SELECT agent_id FROM agent_registry WHERE is_active = 1 ORDER BY rowid ASC LIMIT 1;"
            )
            row = cursor.fetchone()
            if row and row["agent_id"]:
                return str(row["agent_id"])
        return None

    def get_core_roles_status(self) -> List[Tuple[str, Optional[str], Optional[int]]]:
        """Returns a list of tuples containing (role_name, agent_id, is_active)."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                """
                SELECT sr.role_name, sr.agent_id, ar.is_active
                FROM system_roles sr
                LEFT JOIN agent_registry ar ON sr.agent_id = ar.agent_id;
                """
            )
            return [(row["role_name"], row["agent_id"], row["is_active"]) for row in cursor.fetchall()]

    def get_agent_entrypoint_data(self, agent_id: str) -> Optional[Dict[str, str]]:
        """Returns entrypoint module and class name for standard or custom agent loaders."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            try:
                cursor = conn.execute(
                    "SELECT module_path, class_name FROM agent_registry WHERE agent_id = ? AND is_active = 1;",
                    (agent_id,),
                )
                row = cursor.fetchone()
                if row and row["module_path"] and row["class_name"]:
                    return {"module": str(row["module_path"]), "class_name": str(row["class_name"])}
            except Exception:
                pass

            cursor = conn.execute(
                "SELECT agent_id FROM agent_registry WHERE agent_id = ? AND is_active = 1;", (agent_id,)
            )
            if cursor.fetchone():
                return {}

        return None

    def get_agent_display_name(self, agent_id: str) -> Optional[str]:
        """Retrieves display_name for a given agent_id."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute("SELECT display_name FROM agent_registry WHERE agent_id = ?;", (agent_id,))
            row = cursor.fetchone()
            if row and row["display_name"]:
                return str(row["display_name"])
        return None

    def upsert_role_mapping(
        self,
        role_name: str,
        agent_id: Optional[str],
        description: str = "",
        is_mandatory: bool = False,
        is_system_core: bool = False,
    ) -> None:
        """Updates or creates a pointer mapping a system role to a concrete agent."""
        query = """
            INSERT INTO system_roles (role_name, agent_id, description, is_mandatory, is_system_core)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(role_name) DO UPDATE SET
                agent_id = EXCLUDED.agent_id,
                description = EXCLUDED.description,
                is_mandatory = EXCLUDED.is_mandatory,
                is_system_core = EXCLUDED.is_system_core,
                updated_at = CURRENT_TIMESTAMP;
        """
        with get_connection(self.db_path) as conn:
            conn.execute(
                query,
                (role_name, agent_id, description, 1 if is_mandatory else 0, 1 if is_system_core else 0),
            )