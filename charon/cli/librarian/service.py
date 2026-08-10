"""
charon/cli/librarian/service.py

Encapsulated service method for registering skills, performing agent bindings,
and seeding role-based routes according to the V3 database schema.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.CLI.Librarian.Service")


def register_and_bind_skill(
    skill_manifest: Dict[str, Any],
    entry_file_path: Path,
    target_agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    initial_status: str = "ACTIVE",
) -> None:
    """
    Executes skill lifecycle registration in an atomic transaction:
      1. UPSERT into skill_registry (Keyed on skill_id)
      2. INSERT into agent_skill_map (Relational authorization: agent_id <-> skill_id)
      3. UPSERT into route_registry (Action trigger <-> system_roles)
    """
    db_file = db_path or STATE_DB_PATH

    skill_id = skill_manifest["skill_id"]
    version = skill_manifest.get("version", "1.0.0")
    category = skill_manifest.get("category", "General")
    description = skill_manifest.get("description", "")
    sys_reqs = json.dumps(skill_manifest.get("system_requirements", []))
    consumed = json.dumps(skill_manifest.get("consumed_artifacts", []))
    produced = json.dumps(skill_manifest.get("produced_artifacts", []))

    allowed_agents = skill_manifest.get("allowed_agents", ["*"])
    if isinstance(allowed_agents, str):
        allowed_agents = [allowed_agents]

    is_global = 1 if ("*" in allowed_agents or skill_manifest.get("is_global", False)) else 0
    actions: Dict[str, Any] = skill_manifest.get("supported_actions", {})

    with get_connection(db_file) as conn:
        cursor = conn.cursor()

        for action_name, action_def in actions.items():
            if isinstance(action_def, dict):
                act_desc = action_def.get("description", description or f"Executes '{action_name}'")
                handler_name = action_def.get("handler", f"handle_{action_name}")
                params = json.dumps(action_def.get("parameters", {}))
            else:
                act_desc = description or f"Executes '{action_name}'"
                handler_name = action_def
                params = json.dumps({})

            # -----------------------------------------------------------------
            # STEP 1: skill_registry (Primary Key: skill_id)
            # -----------------------------------------------------------------
            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, category, description,
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, status, is_global
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    action_name=excluded.action_name,
                    version=excluded.version,
                    category=excluded.category,
                    description=excluded.description,
                    parameters=excluded.parameters,
                    system_requirements=excluded.system_requirements,
                    consumed_artifacts=excluded.consumed_artifacts,
                    produced_artifacts=excluded.produced_artifacts,
                    entry_file_path=excluded.entry_file_path,
                    handler_name=excluded.handler_name,
                    status=excluded.status,
                    is_global=excluded.is_global,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    skill_id,
                    action_name,
                    version,
                    category,
                    act_desc,
                    params,
                    sys_reqs,
                    consumed,
                    produced,
                    str(entry_file_path.resolve()),
                    handler_name,
                    initial_status,
                    is_global,
                ),
            )

            # -----------------------------------------------------------------
            # STEP 2: agent_skill_map (Maps agent_id <-> skill_id)
            # -----------------------------------------------------------------
            if target_agent_id:
                cursor.execute(
                    """
                    INSERT INTO agent_skill_map (agent_id, skill_id)
                    SELECT agent_id, ? FROM agent_registry WHERE agent_id = ? AND is_active = 1
                    ON CONFLICT(agent_id, skill_id) DO NOTHING
                    """,
                    (skill_id, target_agent_id),
                )
            elif is_global:
                cursor.execute(
                    """
                    INSERT INTO agent_skill_map (agent_id, skill_id)
                    SELECT agent_id, ? FROM agent_registry WHERE is_active = 1
                    ON CONFLICT(agent_id, skill_id) DO NOTHING
                    """,
                    (skill_id,),
                )

            # -----------------------------------------------------------------
            # STEP 3: route_registry (Binds action_trigger -> target_role)
            # -----------------------------------------------------------------
            target_role = None
            if target_agent_id:
                cursor.execute("SELECT role_name FROM system_roles WHERE agent_id = ?", (target_agent_id,))
                role_row = cursor.fetchone()
                if role_row:
                    target_role = role_row[0]

            if not target_role:
                cursor.execute(
                    """
                    SELECT sr.role_name 
                    FROM system_roles sr
                    JOIN agent_skill_map asm ON sr.agent_id = asm.agent_id
                    WHERE asm.skill_id = ?
                    LIMIT 1
                    """,
                    (skill_id,),
                )
                role_row = cursor.fetchone()
                target_role = role_row[0] if role_row else "system_fallback"

            cursor.execute(
                """
                INSERT INTO route_registry (
                    action_trigger, target_role, fallback_role, route_type, is_active, description
                )
                VALUES (?, ?, 'system_fallback', 'DYNAMIC_AUTO', 1, ?)
                ON CONFLICT(action_trigger) DO UPDATE SET
                    target_role = excluded.target_role,
                    description = excluded.description,
                    is_active = 1
                """,
                (action_name, target_role, act_desc),
            )

        conn.commit()
        logger.info(f"[SERVICE] Successfully registered skill '{skill_id}' in state DB.")