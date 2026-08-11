"""
charon/db/repositories/skill.py
System Version: v0.6.0 | File Revision: 6.3.6

Module: Data Access Layer repository for skill dynamic indexing, quarantine lifecycle management,
agent-capability authorization bindings, and CBAC skill permission assignments.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Skill")


class SkillRepository:
    """Data access layer for dynamic skill registry, quarantine lifecycle, and CBAC permissions."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """
        Initializes standard skill, permission binding, and agent mapping tables using CBAC Schema V3.

        Note: Table creation is provided here for bootstrap initialization. Once the database schema
        stabilizes, DDL logic should be executed strictly through a dedicated system migration runner.
        """
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skill_registry (
                    skill_id TEXT PRIMARY KEY,
                    action_name TEXT NOT NULL UNIQUE,
                    version TEXT NOT NULL DEFAULT '1.0.0',
                    category TEXT DEFAULT 'General',
                    description TEXT NOT NULL DEFAULT '',
                    parameters TEXT DEFAULT '{}',
                    system_requirements TEXT NOT NULL DEFAULT '[]',
                    consumed_artifacts TEXT NOT NULL DEFAULT '[]',
                    produced_artifacts TEXT NOT NULL DEFAULT '[]',
                    entry_file_path TEXT NOT NULL,
                    handler_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUARANTINED' CHECK(status IN ('ACTIVE', 'QUARANTINED', 'DISABLED', 'ARCHIVED')),
                    quarantine_reason TEXT DEFAULT NULL,
                    is_global INTEGER DEFAULT 0,
                    indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS skill_permissions (
                    skill_id TEXT NOT NULL,
                    perm_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (skill_id, perm_id),
                    FOREIGN KEY (skill_id) REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
                    FOREIGN KEY (perm_id) REFERENCES permission_registry(perm_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_skill_map (
                    agent_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (agent_id, skill_id),
                    FOREIGN KEY (agent_id) REFERENCES agent_registry(agent_id) ON DELETE CASCADE,
                    FOREIGN KEY (skill_id) REFERENCES skill_registry(skill_id) ON DELETE CASCADE
                );

                -- Persistent backup table to preserve mappings across connection/indexing sweeps
                CREATE TABLE IF NOT EXISTS _bkp_agent_skill_map (
                    agent_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (agent_id, skill_id)
                );

                CREATE INDEX IF NOT EXISTS idx_skill_registry_status ON skill_registry(status);
                CREATE INDEX IF NOT EXISTS idx_skill_permissions_skill ON skill_permissions(skill_id);
                CREATE INDEX IF NOT EXISTS idx_agent_skill_map_agent ON agent_skill_map(agent_id);
                CREATE INDEX IF NOT EXISTS idx_agent_skill_map_skill ON agent_skill_map(skill_id);
            """)

    # =========================================================================
    # 1. REGISTRY CLEANUP & DESERIALIZATION UTILITIES
    # =========================================================================

    def clear_registry(self, clear_agent_mappings: bool = False) -> None:
        """
        Clears indexed skills and permission bindings prior to re-indexing.

        Args:
            clear_agent_mappings: If True, clears agent-skill authorization mappings in addition
                                 to skill registry metadata. Defaults to False to preserve existing
                                 agent capability grants during routine indexing re-sweeps.
        """
        with get_connection(self.db_path) as conn:
            if clear_agent_mappings:
                conn.execute("DELETE FROM agent_skill_map;")
                conn.execute("DELETE FROM _bkp_agent_skill_map;")
                conn.execute("DELETE FROM skill_permissions;")
                conn.execute("DELETE FROM skill_registry;")
            else:
                # Preserve existing agent mappings in a persistent backup table across connection lifecycles
                conn.execute("DELETE FROM _bkp_agent_skill_map;")
                conn.execute("INSERT INTO _bkp_agent_skill_map SELECT * FROM agent_skill_map;")
                conn.execute("DELETE FROM skill_permissions;")
                conn.execute("DELETE FROM skill_registry;")

    def clear_all_skills(self, clear_agent_mappings: bool = False) -> None:
        """Alias for clear_registry to support clean full re-indexing sweeps."""
        self.clear_registry(clear_agent_mappings=clear_agent_mappings)

    def clear_all_agent_skill_mappings(self, agent_id: Optional[str] = None) -> None:
        """
        Clears agent-skill capability mappings.

        Args:
            agent_id: Optional target agent ID. If provided, only clears mappings for that agent.
                      If None, clears all mappings across all agents.
        """
        with get_connection(self.db_path) as conn:
            if agent_id:
                conn.execute("DELETE FROM agent_skill_map WHERE agent_id = ?;", (agent_id,))
                conn.execute("DELETE FROM _bkp_agent_skill_map WHERE agent_id = ?;", (agent_id,))
            else:
                conn.execute("DELETE FROM agent_skill_map;")
                conn.execute("DELETE FROM _bkp_agent_skill_map;")

    def _get_permissions_map_for_skills(
        self, conn: Any, skill_ids: List[str]
    ) -> Dict[str, List[str]]:
        """Batch fetches permissions for multiple skills to eliminate N+1 query patterns."""
        if not skill_ids:
            return {}
        placeholders = ",".join(["?"] * len(skill_ids))
        cursor = conn.execute(
            f"SELECT skill_id, perm_id FROM skill_permissions WHERE skill_id IN ({placeholders});",
            skill_ids,
        )
        perm_map: Dict[str, List[str]] = {sid: [] for sid in skill_ids}
        for r in cursor.fetchall():
            perm_map[r["skill_id"]].append(str(r["perm_id"]))
        return perm_map

    def _parse_skill_row(
        self,
        row: Any,
        conn: Optional[Any] = None,
        permissions_map: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Helper to convert a SQLite Row object to a dictionary and deserialize embedded JSON strings."""
        data = dict(row)
        for json_field in (
            "parameters",
            "system_requirements",
            "consumed_artifacts",
            "produced_artifacts",
        ):
            raw_val = data.get(json_field)
            if isinstance(raw_val, str) and raw_val.strip():
                try:
                    data[json_field] = json.loads(raw_val)
                except Exception:
                    data[json_field] = {} if json_field == "parameters" else []
            elif raw_val is None:
                data[json_field] = {} if json_field == "parameters" else []

        # Populate required primitive CBAC permissions
        skill_id = data.get("skill_id")
        if skill_id:
            if permissions_map is not None:
                data["required_permissions"] = permissions_map.get(skill_id, [])
            elif conn:
                cursor = conn.execute(
                    "SELECT perm_id FROM skill_permissions WHERE skill_id = ?;",
                    (skill_id,),
                )
                data["required_permissions"] = [
                    str(r["perm_id"]) if isinstance(r, dict) else str(r[0])
                    for r in cursor.fetchall()
                ]
            else:
                data["required_permissions"] = self.get_skill_permissions(skill_id)
        else:
            data["required_permissions"] = []

        # Maintain backward compatibility for legacy calls expecting 'is_active' integer
        data["is_active"] = 1 if data.get("status") == "ACTIVE" else 0
        return data

    # =========================================================================
    # 2. SKILL UPSERT & QUARANTINE LIFECYCLE MANAGEMENT
    # =========================================================================

    def upsert_skill(
        self,
        record: Optional[Dict[str, Any]] = None,
        required_permissions: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Inserts or updates a skill record and binds required primitive permissions.
        Defaults status to 'QUARANTINED' unless explicitly supplied as 'ACTIVE'.
        Migrates existing agent mappings safely if the skill_id changed.
        """
        rec = dict(record) if record else {}
        rec.update(kwargs)

        req_perms = required_permissions or rec.pop("required_permissions", None)

        rec.setdefault("version", "1.0.0")
        rec.setdefault("category", "General")
        rec.setdefault("description", "")
        rec.setdefault("status", "QUARANTINED")
        rec.setdefault("quarantine_reason", None)
        rec.setdefault("is_global", 0)

        # Convert boolean is_active to CBAC status string if legacy record passed
        if "is_active" in rec and "status" not in rec:
            rec["status"] = "ACTIVE" if rec["is_active"] else "DISABLED"

        for field in (
            "parameters",
            "system_requirements",
            "consumed_artifacts",
            "produced_artifacts",
        ):
            val = rec.get(field)
            if val is not None and not isinstance(val, str):
                rec[field] = json.dumps(val)
            elif val is None:
                rec[field] = "{}" if field == "parameters" else "[]"

        query = """
            INSERT INTO skill_registry (
                skill_id, action_name, version, category, description,
                parameters, system_requirements, consumed_artifacts, produced_artifacts,
                entry_file_path, handler_name, status, quarantine_reason, is_global
            ) VALUES (
                :skill_id, :action_name, :version, :category, :description,
                :parameters, :system_requirements, :consumed_artifacts, :produced_artifacts,
                :entry_file_path, :handler_name, :status, :quarantine_reason, :is_global
            )
            ON CONFLICT(skill_id) DO UPDATE SET
                action_name=EXCLUDED.action_name,
                version=EXCLUDED.version,
                category=EXCLUDED.category,
                description=EXCLUDED.description,
                parameters=EXCLUDED.parameters,
                system_requirements=EXCLUDED.system_requirements,
                consumed_artifacts=EXCLUDED.consumed_artifacts,
                produced_artifacts=EXCLUDED.produced_artifacts,
                entry_file_path=EXCLUDED.entry_file_path,
                handler_name=EXCLUDED.handler_name,
                status=EXCLUDED.status,
                quarantine_reason=EXCLUDED.quarantine_reason,
                is_global=EXCLUDED.is_global,
                updated_at=CURRENT_TIMESTAMP;
        """
        with get_connection(self.db_path) as conn:
            # Locate any previous skill entry that shares action_name under a different skill_id
            cursor = conn.execute(
                "SELECT skill_id FROM skill_registry WHERE action_name = ? AND skill_id != ?;",
                (rec["action_name"], rec["skill_id"]),
            )
            old_row = cursor.fetchone()

            if old_row:
                old_skill_id = old_row[0] if isinstance(old_row, (tuple, list)) else old_row["skill_id"]

                # Remove potential duplicate mappings that would block UPDATE
                conn.execute(
                    "DELETE FROM agent_skill_map WHERE skill_id = ? AND agent_id IN ("
                    "  SELECT agent_id FROM agent_skill_map WHERE skill_id = ?"
                    ");",
                    (old_skill_id, rec["skill_id"]),
                )
                conn.execute(
                    "UPDATE agent_skill_map SET skill_id = ? WHERE skill_id = ?;",
                    (rec["skill_id"], old_skill_id),
                )
                conn.execute(
                    "DELETE FROM skill_permissions WHERE skill_id = ? AND perm_id IN ("
                    "  SELECT perm_id FROM skill_permissions WHERE skill_id = ?"
                    ");",
                    (old_skill_id, rec["skill_id"]),
                )
                conn.execute(
                    "UPDATE skill_permissions SET skill_id = ? WHERE skill_id = ?;",
                    (rec["skill_id"], old_skill_id),
                )
                # Safely delete old parent record now that children are re-linked
                conn.execute("DELETE FROM skill_registry WHERE skill_id = ?;", (old_skill_id,))

            conn.execute(query, rec)

            # Restore mapped permissions from persistent backup table if re-indexing cleared registry
            try:
                conn.execute(
                    """
                    INSERT INTO agent_skill_map (agent_id, skill_id, created_at)
                    SELECT agent_id, skill_id, created_at FROM _bkp_agent_skill_map
                    WHERE skill_id = ?
                    ON CONFLICT(agent_id, skill_id) DO NOTHING;
                    """,
                    (rec["skill_id"],),
                )
            except Exception as e:
                logger.debug("Skip agent_skill_map backup restore: %s", e)

            # Bind CBAC permissions if provided
            if req_perms:
                for perm_id in req_perms:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO skill_permissions (skill_id, perm_id) VALUES (?, ?);",
                            (rec["skill_id"], perm_id),
                        )
                    except Exception as pe:
                        logger.warning(
                            "Could not bind permission '%s' to skill '%s': %s",
                            perm_id,
                            rec["skill_id"],
                            pe,
                        )

    def promote_skill(self, skill_id: str) -> bool:
        """Promotes a quarantined skill to ACTIVE status."""
        query = """
            UPDATE skill_registry 
            SET status = 'ACTIVE', quarantine_reason = NULL, updated_at = CURRENT_TIMESTAMP 
            WHERE skill_id = ?;
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (skill_id,))
            return cursor.rowcount > 0

    def quarantine_skill(self, skill_id: str, reason: str) -> bool:
        """Forces a skill into QUARANTINED status with an explicit reason."""
        query = """
            UPDATE skill_registry 
            SET status = 'QUARANTINED', quarantine_reason = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE skill_id = ?;
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (reason, skill_id))
            return cursor.rowcount > 0

    def set_skill_active_status(self, skill_id: str, is_active: bool) -> bool:
        """Enables ('ACTIVE') or disables ('DISABLED') a specific skill in the database."""
        status = "ACTIVE" if is_active else "DISABLED"
        query = "UPDATE skill_registry SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE skill_id = ?;"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (status, skill_id))
            return cursor.rowcount > 0

    # =========================================================================
    # 3. QUERY & READ OPERATIONS
    # =========================================================================

    def get_all_active_skills(self) -> List[Dict[str, Any]]:
        """Fetches all ACTIVE skills from the registry using a read-only transaction."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_registry WHERE status = 'ACTIVE';"
            )
            rows = cursor.fetchall()
            skill_ids = [r["skill_id"] for r in rows]
            perm_map = self._get_permissions_map_for_skills(conn, skill_ids)
            return [self._parse_skill_row(row, conn, perm_map) for row in rows]

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """Alias for get_all_active_skills."""
        return self.get_all_active_skills()

    def get_skill_by_action(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves an active skill manifest directly by action trigger name or skill_id."""
        query = """
            SELECT 
                skill_id,
                action_name,
                version,
                category,
                description,
                parameters,
                system_requirements,
                consumed_artifacts,
                produced_artifacts,
                entry_file_path,
                handler_name,
                status,
                quarantine_reason,
                is_global
            FROM skill_registry 
            WHERE (action_name = ? OR skill_id = ?) 
              AND status = 'ACTIVE' 
            LIMIT 1;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (action_name, action_name))
            row = cursor.fetchone()
            if not row:
                return None
            perm_map = self._get_permissions_map_for_skills(conn, [row["skill_id"]])
            return self._parse_skill_row(row, conn, perm_map)

    def get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves skill metadata directly by unique skill_id regardless of status."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_registry WHERE skill_id = ?;",
                (skill_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            perm_map = self._get_permissions_map_for_skills(conn, [skill_id])
            return self._parse_skill_row(row, conn, perm_map)

    def get_skill_permissions(self, skill_id: str) -> List[str]:
        """Fetches all primitive permission IDs bound to a given skill."""
        query = "SELECT perm_id FROM skill_permissions WHERE skill_id = ?;"
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (skill_id,))
            return [str(row["perm_id"]) for row in cursor.fetchall()]

    # =========================================================================
    # 4. GRANULAR AGENT & SKILL PERMISSIONS (`agent_skill_map`)
    # =========================================================================

    def grant_agent_skill(self, agent_id: str, action_name: str) -> bool:
        """Grants capability to an agent for an action by resolving its skill_id."""
        query = """
            INSERT INTO agent_skill_map (agent_id, skill_id)
            SELECT ?, skill_id
            FROM skill_registry
            WHERE action_name = ?
            ON CONFLICT DO NOTHING;
        """
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(query, (agent_id, action_name))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                "Failed to grant action '%s' to agent '%s': %s",
                action_name,
                agent_id,
                e,
            )
            return False

    def revoke_agent_skill(self, agent_id: str, action_name: str) -> bool:
        """Revokes capability from an agent for an action by resolving its skill_id."""
        query = """
            DELETE FROM agent_skill_map
            WHERE agent_id = ? AND skill_id = (
                SELECT skill_id FROM skill_registry WHERE action_name = ?
            );
        """
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(query, (agent_id, action_name))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                "Failed to revoke action '%s' from agent '%s': %s",
                action_name,
                agent_id,
                e,
            )
            return False

    def link_agent_to_skill(self, agent_id: str, skill_id: str) -> bool:
        """Directly links an agent to a specific skill_id."""
        return self.grant_skill_by_id(agent_id, skill_id)

    def grant_skill_by_id(self, agent_id: str, skill_id: str) -> bool:
        """Directly grants a skill implementation to an agent using skill_id."""
        query = """
            INSERT INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING;
        """
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(query, (agent_id, skill_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                "Failed to grant skill_id '%s' to agent '%s': %s",
                skill_id,
                agent_id,
                e,
            )
            return False

    def revoke_skill_by_id(self, agent_id: str, skill_id: str) -> bool:
        """Directly revokes a skill implementation from an agent using skill_id."""
        query = "DELETE FROM agent_skill_map WHERE agent_id = ? AND skill_id = ?;"
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(query, (agent_id, skill_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                "Failed to revoke skill_id '%s' from agent '%s': %s",
                skill_id,
                agent_id,
                e,
            )
            return False

    def get_actions_for_agent(
        self, agent_id: str, alt_agent_id: Optional[str] = None
    ) -> List[str]:
        """Fetches distinct ACTIVE action capability keys strictly granted to an agent (or marked global)."""
        target_id = agent_id  # Do not union-bleed skills from alt_agent_id
        query = """
            SELECT DISTINCT sr.action_name
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.status = 'ACTIVE'
              AND (sr.is_global = 1 OR asm.agent_id IN (?, '*'))
            ORDER BY sr.action_name ASC;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (target_id,))
            return [str(row["action_name"]) for row in cursor.fetchall()]

    def get_skills_for_agent(
        self, agent_id: str, alt_agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches full skill dictionary records for ACTIVE actions accessible to an agent."""
        target_id = agent_id
        query = """
            SELECT DISTINCT sr.*
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.status = 'ACTIVE'
              AND (sr.is_global = 1 OR asm.agent_id IN (?, '*'))
            ORDER BY sr.skill_id ASC;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (target_id,))
            rows = cursor.fetchall()
            skill_ids = [r["skill_id"] for r in rows]
            perm_map = self._get_permissions_map_for_skills(conn, skill_ids)
            return [self._parse_skill_row(row, conn, perm_map) for row in rows]

    def is_skill_available(
        self, action_name: str, agent_id: str, alt_agent_id: Optional[str] = None
    ) -> bool:
        """Verifies if an action contract is ACTIVE and accessible by an agent."""
        target_id = agent_id
        query = """
            SELECT 1
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.action_name = ?
              AND sr.status = 'ACTIVE'
              AND (sr.is_global = 1 OR asm.agent_id IN (?, '*'))
            LIMIT 1;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (action_name, target_id))
            return cursor.fetchone() is not None

    def get_agents_for_action(self, action_name: str) -> List[str]:
        """Fetches a list of agent_ids authorized to execute an ACTIVE action capability."""
        query = """
            SELECT DISTINCT 
                CASE 
                    WHEN sr.is_global = 1 THEN '*'
                    ELSE asm.agent_id 
                END AS agent_id
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.action_name = ?
              AND sr.status = 'ACTIVE'
              AND (sr.is_global = 1 OR asm.agent_id IS NOT NULL);
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (action_name,))
            return [str(row["agent_id"]) for row in cursor.fetchall() if row["agent_id"]]

    def get_equipped_skills_for_agent(self, agent_id: str) -> List[str]:
        """Fetches distinct ACTIVE skill_ids equipped to an agent via agent_skill_map or global flag."""
        query = """
            SELECT DISTINCT sr.skill_id
            FROM skill_registry sr
            LEFT JOIN agent_skill_map asm ON sr.skill_id = asm.skill_id
            WHERE sr.status = 'ACTIVE'
              AND (sr.is_global = 1 OR asm.agent_id IN (?, '*'));
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (agent_id,))
            return [str(row["skill_id"]) for row in cursor.fetchall()]