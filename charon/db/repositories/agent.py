"""
charon/db/repositories/agent.py
System Version: v0.6.2 | File Revision: 6.1.0

Module: Data Access Layer repository for agent configurations, capability descriptions,
triage priority weights, system prompts, and action capability manifests.
Strictly relies on Database as SSOT with zero code-level fallback synthesis.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Agent")


class AgentRepository:
    """Data access layer for agent configurations, routing manifests, and prompts."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)

    @contextmanager
    def _managed_conn(self, conn: Optional[sqlite3.Connection] = None, **kwargs):
        """Yields the injected connection or provisions a new one from the pool."""
        if conn:
            yield conn
        else:
            with get_connection(self.db_path, **kwargs) as new_conn:
                yield new_conn

    def ensure_schema(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Initializes agent_registry table and executes schema migrations at startup."""
        with self._managed_conn(conn) as db_conn:
            db_conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_registry (
                    agent_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    default_action TEXT DEFAULT '',
                    system_prompt TEXT DEFAULT '',
                    priority_weight REAL DEFAULT 1.0,
                    override_triggers TEXT DEFAULT '[]',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_agent_registry_is_active ON agent_registry(is_active);
            """)

            cursor = db_conn.execute("PRAGMA table_info(agent_registry);")
            existing_columns = {row[1] for row in cursor.fetchall()}

            migrations = {
                "priority_weight": "REAL DEFAULT 1.0",
                "override_triggers": "TEXT DEFAULT '[]'",
            }

            for col_name, col_type in migrations.items():
                if col_name not in existing_columns:
                    logger.info(
                        f"[AgentRepository] Migrating schema: adding '{col_name}' column to agent_registry."
                    )
                    db_conn.execute(
                        f"ALTER TABLE agent_registry ADD COLUMN {col_name} {col_type};"
                    )

    # =========================================================================
    # 1. HELPER & RESOLUTION UTILITIES
    # =========================================================================

    def _parse_agent_row(self, row: Any) -> Dict[str, Any]:
        """Converts an agent Row object into a dictionary with deserialized JSON fields."""
        data = dict(row)

        if "priority_weight" in data:
            data["priority_weight"] = (
                float(data["priority_weight"])
                if data["priority_weight"] is not None
                else 1.0
            )

        triggers = data.get("override_triggers")
        if isinstance(triggers, str) and triggers.strip():
            try:
                data["override_triggers"] = json.loads(triggers)
            except json.JSONDecodeError as e:
                logger.error(
                    f"[AgentRepository] Malformed JSON in override_triggers for agent '{data.get('agent_id')}': {e}"
                )
                raise
        elif not isinstance(triggers, list):
            data["override_triggers"] = []

        if "is_active" in data:
            data["is_active"] = bool(data["is_active"])

        return data

    def resolve_agent_id(self, identifier: str, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
        """
        SSOT Identifier Resolver.
        Queries SQLite to map any raw identifier (agent_id, display_name, or system_role)
        directly to its canonical agent_id. Performs NO Python string manipulation.
        """
        if not identifier or not str(identifier).strip():
            return None

        clean_id = str(identifier).strip()

        # Query checks canonical ID, display name, and system_roles table mapping
        query = """
            SELECT a.agent_id
            FROM agent_registry a
            LEFT JOIN system_roles sr ON sr.agent_id = a.agent_id
            WHERE LOWER(a.agent_id) = LOWER(?)
               OR LOWER(a.display_name) = LOWER(?)
               OR LOWER(sr.role_id) = LOWER(?)
            LIMIT 1;
        """
        with self._managed_conn(conn, read_only=True) as db_conn:
            cursor = db_conn.execute(query, (clean_id, clean_id, clean_id))
            row = cursor.fetchone()
            if row:
                return str(row[0])

            logger.warning(
                f"[AgentRepository] Fail Fast: Identifier '{clean_id}' could not be resolved in database."
            )
            return None

    # =========================================================================
    # 2. WRITE & UPSERT OPERATIONS
    # =========================================================================

    def upsert_agent(
        self,
        record: Optional[Dict[str, Any]] = None,
        conn: Optional[sqlite3.Connection] = None,
        **kwargs: Any,
    ) -> bool:
        """Inserts or updates an agent record in the agent_registry table."""
        rec = dict(record) if record else {}
        rec.update(kwargs)

        if "agent_id" not in rec or "display_name" not in rec:
            raise ValueError("Agent record must contain at least 'agent_id' and 'display_name'.")

        rec.setdefault("description", "")
        rec.setdefault("default_action", "")
        rec.setdefault("system_prompt", "")
        rec.setdefault("priority_weight", 1.0)
        rec.setdefault("is_active", 1)

        rec["priority_weight"] = float(rec["priority_weight"])

        if isinstance(rec["is_active"], bool):
            rec["is_active"] = 1 if rec["is_active"] else 0

        triggers = rec.get("override_triggers", [])
        if not isinstance(triggers, str):
            rec["override_triggers"] = json.dumps(triggers if isinstance(triggers, list) else [])

        query = """
            INSERT INTO agent_registry (
                agent_id, display_name, description, default_action,
                system_prompt, priority_weight, override_triggers, is_active
            ) VALUES (
                :agent_id, :display_name, :description, :default_action,
                :system_prompt, :priority_weight, :override_triggers, :is_active
            )
            ON CONFLICT(agent_id) DO UPDATE SET
                display_name=EXCLUDED.display_name,
                description=EXCLUDED.description,
                default_action=EXCLUDED.default_action,
                system_prompt=EXCLUDED.system_prompt,
                priority_weight=EXCLUDED.priority_weight,
                override_triggers=EXCLUDED.override_triggers,
                is_active=EXCLUDED.is_active,
                updated_at=CURRENT_TIMESTAMP;
        """
        with self._managed_conn(conn) as db_conn:
            db_conn.execute(query, rec)
        logger.info(f"[AgentRepository] Upserted agent record for '{rec['agent_id']}'.")
        return True

    def update_manifest(self, agent_id: str, update_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
        """Persists updated capability prompts, weights, triggers, or statuses to DB."""
        fields = []
        params = []

        if "display_name" in update_data:
            fields.append("display_name = ?")
            params.append(update_data["display_name"])
        if "description" in update_data:
            fields.append("description = ?")
            params.append(update_data["description"])
        if "default_action" in update_data:
            fields.append("default_action = ?")
            params.append(update_data["default_action"])
        if "system_prompt" in update_data:
            fields.append("system_prompt = ?")
            params.append(update_data["system_prompt"])
        if "priority_weight" in update_data:
            fields.append("priority_weight = ?")
            params.append(float(update_data["priority_weight"]))
        if "override_triggers" in update_data:
            triggers = update_data["override_triggers"]
            serialized = triggers if isinstance(triggers, str) else json.dumps(triggers)
            fields.append("override_triggers = ?")
            params.append(serialized)
        if "is_active" in update_data:
            fields.append("is_active = ?")
            params.append(1 if update_data["is_active"] else 0)

        if not fields:
            return True

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(agent_id)

        query = f"UPDATE agent_registry SET {', '.join(fields)} WHERE agent_id = ?"

        with self._managed_conn(conn) as db_conn:
            cursor = db_conn.execute(query, params)
            if cursor.rowcount == 0:
                logger.warning(f"[AgentRepository] Agent '{agent_id}' not found for update.")
                return False
        logger.info(f"[AgentRepository] Updated manifest for agent '{agent_id}'.")
        return True

    def set_tool_status(self, agent_id: str, tool_identifier: str, enabled: bool, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Enables or revokes an agent capability in agent_skill_map."""
        with self._managed_conn(conn, row_factory=True) as db_conn:
            cursor = db_conn.execute(
                "SELECT skill_id FROM skill_registry WHERE action_name = ? OR skill_id = ? LIMIT 1;",
                (tool_identifier, tool_identifier),
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(
                    f"[AgentRepository] Skill/tool '{tool_identifier}' not found in registry."
                )
                return False

            skill_id = row["skill_id"]

            if enabled:
                db_conn.execute(
                    "INSERT INTO agent_skill_map (agent_id, skill_id) VALUES (?, ?) ON CONFLICT DO NOTHING;",
                    (agent_id, skill_id),
                )
            else:
                db_conn.execute(
                    "DELETE FROM agent_skill_map WHERE agent_id = ? AND skill_id = ?;",
                    (agent_id, skill_id),
                )
        logger.info(
            f"[AgentRepository] Set tool '{tool_identifier}' enabled={enabled} for agent '{agent_id}'."
        )
        return True

    def delete_agent(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Deletes an agent record from the database."""
        with self._managed_conn(conn) as db_conn:
            cursor = db_conn.execute("DELETE FROM agent_registry WHERE agent_id = ?;", (agent_id,))
            return cursor.rowcount > 0

    def clear_all_agents(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Clears all agents from agent_registry."""
        with self._managed_conn(conn) as db_conn:
            db_conn.execute("DELETE FROM agent_registry;")

    # =========================================================================
    # 3. READ & MANIFEST QUERY OPERATIONS (STRICT DB TRUTH)
    # =========================================================================

    def get_active_agent(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """Retrieves active agent metadata and system prompt by agent_id."""
        with self._managed_conn(conn, read_only=True, row_factory=True) as db_conn:
            cursor = db_conn.execute(
                """
                SELECT agent_id, display_name, description, default_action,
                       system_prompt, priority_weight, override_triggers, is_active
                FROM agent_registry
                WHERE agent_id = ? AND is_active = 1;
                """,
                (agent_id,),
            )
            row = cursor.fetchone()
            return self._parse_agent_row(row) if row else None

    def get_active_agent_ids(self, conn: Optional[sqlite3.Connection] = None) -> List[str]:
        """Retrieves a list of all active agent_ids registered in the system."""
        with self._managed_conn(conn, read_only=True, row_factory=True) as db_conn:
            cursor = db_conn.execute(
                "SELECT agent_id FROM agent_registry WHERE is_active = 1 ORDER BY agent_id ASC;"
            )
            return [str(row["agent_id"]) for row in cursor.fetchall()]

    def get_all_active_agents(self, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        """Retrieves all active agent dicts from the database."""
        with self._managed_conn(conn, read_only=True, row_factory=True) as db_conn:
            cursor = db_conn.execute(
                """
                SELECT agent_id, display_name, description, system_prompt, default_action,
                       priority_weight, override_triggers, is_active
                FROM agent_registry 
                WHERE is_active = 1
                ORDER BY priority_weight DESC, agent_id ASC;
                """
            )
            return [self._parse_agent_row(row) for row in cursor.fetchall()]

    def get_all_manifests(self, active_only: bool = True, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Dict[str, Any]]:
        """Retrieves registered agent manifests strictly from agent_skill_map bindings."""
        where_clause = "WHERE a.is_active = 1" if active_only else ""
        query = f"""
            SELECT 
                a.agent_id,
                a.display_name,
                a.description,
                a.default_action,
                a.system_prompt,
                a.priority_weight,
                a.override_triggers,
                a.is_active,
                s.skill_id,
                s.action_name,
                s.description AS skill_description,
                s.parameters,
                s.status AS skill_status
            FROM agent_registry a
            LEFT JOIN agent_skill_map asm ON asm.agent_id = a.agent_id
            LEFT JOIN skill_registry s ON s.skill_id = asm.skill_id AND s.status = 'ACTIVE'
            {where_clause}
            ORDER BY a.priority_weight DESC, a.agent_id ASC;
        """
        with self._managed_conn(conn, read_only=True, row_factory=True) as db_conn:
            cursor = db_conn.execute(query)
            rows = cursor.fetchall()

            manifests: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                agent_id = row["agent_id"]
                if agent_id not in manifests:
                    parsed_agent = self._parse_agent_row(row)
                    weight_val = parsed_agent["priority_weight"]

                    manifests[agent_id] = {
                        "agent_id": agent_id,
                        "display_name": row["display_name"],
                        "description": row["description"] or "",
                        "system_prompt": row["system_prompt"] or "",
                        "default_action": row["default_action"] or "",
                        "priority_weight": weight_val,
                        "override_triggers": parsed_agent["override_triggers"],
                        "is_active": parsed_agent["is_active"],
                        "equipped_skills": [],
                        "active_tools": [],
                        "skills": [],
                        "actions": {},
                    }

                if row["skill_id"]:
                    action_name = row["action_name"]
                    params = row["parameters"]
                    if isinstance(params, str) and params.strip():
                        try:
                            params = json.loads(params)
                        except json.JSONDecodeError:
                            logger.error(
                                f"[AgentRepository] Malformed parameter JSON for skill '{row['skill_id']}'"
                            )
                            raise
                    elif not isinstance(params, dict):
                        params = {}

                    skill_info = {
                        "skill_id": row["skill_id"],
                        "action_name": action_name,
                        "description": row["skill_description"] or "",
                        "parameters": params,
                    }

                    if row["skill_id"] not in manifests[agent_id]["equipped_skills"]:
                        manifests[agent_id]["equipped_skills"].append(row["skill_id"])
                        manifests[agent_id]["active_tools"].append(action_name)
                        manifests[agent_id]["skills"].append({
                            "skill_id": row["skill_id"],
                            "action_name": action_name,
                        })
                        manifests[agent_id]["actions"][action_name] = skill_info

            return manifests

    def get_manifest(self, agent_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """Fetches a single agent manifest strictly using explicit database relationships."""
        manifests = self.get_all_manifests(active_only=False, conn=conn)
        return manifests.get(agent_id)