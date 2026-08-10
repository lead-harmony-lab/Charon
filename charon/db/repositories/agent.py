"""
charon/db/repositories/agent.py
System Version: v0.6.0 | File Revision: 5.3.0

Module: Data Access Layer repository for agent configurations, capability descriptions,
triage priority weights, system prompts, and action capability manifests.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Agent")


class AgentRepository:
    """Data access layer for agent configurations, routing manifests, and prompts."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """Initializes agent_registry table and executes schema migrations if needed at startup."""
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_registry (
                    agent_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    default_action TEXT NOT NULL DEFAULT 'answer_query',
                    system_prompt TEXT DEFAULT '',
                    priority_weight REAL DEFAULT 1.0,
                    override_triggers TEXT DEFAULT '[]',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor = conn.execute("PRAGMA table_info(agent_registry);")
            existing_columns = {row[1] for row in cursor.fetchall()}

            migrations = {
                "priority_weight": "REAL DEFAULT 1.0",
                "override_triggers": "TEXT DEFAULT '[]'",
            }

            for col_name, col_type in migrations.items():
                if col_name not in existing_columns:
                    logger.info(f"[AgentRepository] Migrating schema: adding '{col_name}' column to agent_registry.")
                    conn.execute(f"ALTER TABLE agent_registry ADD COLUMN {col_name} {col_type};")

    def get_active_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves active agent metadata and system prompt by agent_id."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT agent_id, display_name, system_prompt FROM agent_registry WHERE agent_id = ? AND is_active = 1;",
                (agent_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_agent_ids(self) -> List[str]:
        """Retrieves a list of all active agent_ids registered in the system."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute("SELECT agent_id FROM agent_registry WHERE is_active = 1;")
            return [str(row["agent_id"]) for row in cursor.fetchall()]

    def get_all_manifests(self) -> Dict[str, Dict[str, Any]]:
        """Retrieves registered agent manifests and populates capabilities dynamically from agent_skill_map and skill_registry."""
        query = """
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
            LEFT JOIN agent_skill_map asm ON (a.agent_id = asm.agent_id OR asm.agent_id = '*')
            LEFT JOIN skill_registry s ON asm.skill_id = s.skill_id AND s.status = 'ACTIVE';
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()

        manifests: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            agent_id = row["agent_id"]
            if agent_id not in manifests:
                weight_val = float(row["priority_weight"]) if row["priority_weight"] is not None else 1.0
                manifests[agent_id] = {
                    "agent_id": agent_id,
                    "name": row["display_name"],
                    "display_name": row["display_name"],
                    "description": row["description"] or "",
                    "system_prompt": row["system_prompt"] or "",
                    "default_action": row["default_action"] or "",
                    "weight": weight_val,
                    "priority_weight": weight_val,
                    "override_triggers": json.loads(row["override_triggers"] or "[]"),
                    "status": "active" if row["is_active"] == 1 else "disabled",
                    "is_active": bool(row["is_active"]),
                    "equipped_skills": [],
                    "active_tools": [],
                    "skills": [],
                    "actions": {},
                }

            if row["skill_id"]:
                action_name = row["action_name"]

                # Safely parse JSON parameters
                params = row["parameters"]
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}
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

    def get_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Fetches an agent manifest and all associated active skill capabilities."""
        query = """
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
            LEFT JOIN agent_skill_map asm ON (a.agent_id = asm.agent_id OR asm.agent_id = '*')
            LEFT JOIN skill_registry s ON asm.skill_id = s.skill_id AND s.status = 'ACTIVE'
            WHERE a.agent_id = ? AND a.is_active = 1;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (agent_id,))
            rows = cursor.fetchall()

        if not rows:
            return None

        first = rows[0]
        weight_val = float(first["priority_weight"]) if first["priority_weight"] is not None else 1.0

        manifest = {
            "agent_id": first["agent_id"],
            "name": first["display_name"],
            "display_name": first["display_name"],
            "description": first["description"] or "",
            "system_prompt": first["system_prompt"] or "",
            "default_action": first["default_action"] or "",
            "weight": weight_val,
            "priority_weight": weight_val,
            "override_triggers": json.loads(first["override_triggers"] or "[]"),
            "status": "active" if first["is_active"] == 1 else "disabled",
            "is_active": bool(first["is_active"]),
            "equipped_skills": [],
            "active_tools": [],
            "skills": [],
            "actions": {},
        }

        for row in rows:
            if row["skill_id"]:
                action_name = row["action_name"]

                params = row["parameters"]
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}
                elif not isinstance(params, dict):
                    params = {}

                skill_info = {
                    "skill_id": row["skill_id"],
                    "action_name": action_name,
                    "description": row["skill_description"] or "",
                    "parameters": params,
                }

                if row["skill_id"] not in manifest["equipped_skills"]:
                    manifest["equipped_skills"].append(row["skill_id"])
                    manifest["active_tools"].append(action_name)
                    manifest["skills"].append({
                        "skill_id": row["skill_id"],
                        "action_name": action_name,
                    })
                    manifest["actions"][action_name] = skill_info

        return manifest

    def update_manifest(self, agent_id: str, update_data: Dict[str, Any]) -> bool:
        """Persists updated capability prompts, weights, triggers, or description to DB."""
        fields = []
        params = []

        if "description" in update_data:
            fields.append("description = ?")
            params.append(update_data["description"])
        if "system_prompt" in update_data:
            fields.append("system_prompt = ?")
            params.append(update_data["system_prompt"])
        if "priority_weight" in update_data:
            fields.append("priority_weight = ?")
            params.append(float(update_data["priority_weight"]))
        if "override_triggers" in update_data:
            fields.append("override_triggers = ?")
            params.append(json.dumps(update_data["override_triggers"]))

        if not fields:
            return True

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(agent_id)

        query = f"UPDATE agent_registry SET {', '.join(fields)} WHERE agent_id = ?"

        try:
            with get_connection(self.db_path) as conn:
                conn.execute(query, params)
            logger.info(f"[AgentRepository] Updated manifest for agent '{agent_id}'.")
            return True
        except Exception as e:
            logger.error(f"[AgentRepository] Failed to update manifest for agent '{agent_id}': {e}", exc_info=True)
            return False

    def set_tool_status(self, agent_id: str, tool_identifier: str, enabled: bool) -> bool:
        """Enables or revokes an agent capability in agent_skill_map."""
        try:
            with get_connection(self.db_path, row_factory=True) as conn:
                cursor = conn.execute(
                    "SELECT skill_id FROM skill_registry WHERE action_name = ? OR skill_id = ? LIMIT 1;",
                    (tool_identifier, tool_identifier),
                )
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"[AgentRepository] Skill/tool '{tool_identifier}' not found in registry.")
                    return False

                skill_id = row["skill_id"]

                if enabled:
                    conn.execute(
                        "INSERT INTO agent_skill_map (agent_id, skill_id) VALUES (?, ?) ON CONFLICT DO NOTHING;",
                        (agent_id, skill_id),
                    )
                else:
                    conn.execute(
                        "DELETE FROM agent_skill_map WHERE agent_id = ? AND skill_id = ?;",
                        (agent_id, skill_id),
                    )
            logger.info(f"[AgentRepository] Set tool '{tool_identifier}' enabled={enabled} for agent '{agent_id}'.")
            return True
        except Exception as e:
            logger.error(f"[AgentRepository] Failed tool toggle for agent '{agent_id}': {e}", exc_info=True)
            return False

    def get_all_active_agents(self) -> List[Dict[str, Any]]:
        """Retrieves all active agent dicts from the database."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                """
                SELECT agent_id, display_name, description, system_prompt, default_action,
                       priority_weight, override_triggers, is_active
                FROM agent_registry 
                WHERE is_active = 1;
                """
            )
            return [dict(row) for row in cursor.fetchall()]