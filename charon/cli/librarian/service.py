"""
charon/cli/librarian/service.py
System Version: v0.2.0 | File Revision: 2.0.0

Encapsulated service methods for registering skills, performing targeted agent bindings,
and seeding role-based routes according to the V3 database schema.
Guarantees strict isolation on all mutations and deletion operations.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.service")


def register_and_bind_skill(
    skill_manifest: Dict[str, Any],
    entry_file_path: Path,
    target_agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    initial_status: str = "ACTIVE",
) -> None:
    """
    Executes skill lifecycle registration in an atomic, scoped transaction:
      1. UPSERT into skill_registry (Keyed on skill_id, action_name)
      2. INSERT into agent_skill_map (Relational authorization: agent_id <-> skill_id)
      3. UPSERT into route_registry (Action trigger <-> system_roles)
    """
    db_file = db_path or STATE_DB_PATH

    skill_id = skill_manifest.get("skill_id")
    if not skill_id:
        raise ValueError("Skill manifest must contain a valid 'skill_id'.")

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

    # Default fallback if no supported_actions defined
    if not actions:
        actions = {skill_id: {"description": description, "handler_name": "handle_default"}}

    resolved_entry_path = str(entry_file_path.resolve())

    with get_connection(db_file) as conn:
        cursor = conn.cursor()

        # -----------------------------------------------------------------
        # STEP 1: skill_registry (UPSERT action rows for this skill)
        # -----------------------------------------------------------------
        for action_name, action_def in actions.items():
            if isinstance(action_def, dict):
                act_desc = action_def.get("description") or description or f"Executes '{action_name}'"
                handler_name = (
                    action_def.get("handler_name")
                    or action_def.get("handler")
                    or f"handle_{action_name}"
                )
                params = json.dumps(action_def.get("parameters", {}))
            else:
                act_desc = description or f"Executes '{action_name}'"
                handler_name = str(action_def) if action_def else f"handle_{action_name}"
                params = json.dumps({})

            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, category, description,
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, status, is_global
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id, action_name) DO UPDATE SET
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
                    resolved_entry_path,
                    handler_name,
                    initial_status,
                    is_global,
                ),
            )

            # -------------------------------------------------------------
            # STEP 2: route_registry (Binds action_trigger -> target_role)
            # -------------------------------------------------------------
            target_role = None
            if target_agent_id:
                cursor.execute(
                    "SELECT role_name FROM system_roles WHERE agent_id = ?",
                    (target_agent_id,)
                )
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

        # -----------------------------------------------------------------
        # STEP 3: agent_skill_map (Maps agent_id <-> skill_id)
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
        else:
            # Explicitly bind specifically allowed agents
            for agent_id in allowed_agents:
                if agent_id and agent_id != "*":
                    cursor.execute(
                        """
                        INSERT INTO agent_skill_map (agent_id, skill_id)
                        SELECT agent_id, ? FROM agent_registry WHERE agent_id = ? AND is_active = 1
                        ON CONFLICT(agent_id, skill_id) DO NOTHING
                        """,
                        (skill_id, agent_id),
                    )

        conn.commit()
        logger.info(f"[SERVICE] Successfully registered skill '{skill_id}' in state DB.")


def unregister_skill(
    skill_id: str,
    db_path: Optional[Path] = None,
) -> None:
    """
    Safely unregisters a single skill from the database.

    ISOLATION GUARANTEE:
    - Scoped strictly to the provided `skill_id`.
    - Purges matching rows in `skill_registry` and `agent_skill_map`.
    - Removes corresponding `route_registry` triggers bound to this skill's actions.
    - NEVER wipes or alters unrelated skill or agent records.
    """
    if not skill_id:
        logger.warning("[SERVICE] Empty skill_id passed to unregister_skill. Aborting.")
        return

    db_file = db_path or STATE_DB_PATH
    if not db_file.exists():
        return

    with get_connection(db_file) as conn:
        cursor = conn.cursor()

        # Find action triggers associated with this skill to clean route_registry safely
        cursor.execute("SELECT action_name FROM skill_registry WHERE skill_id = ?", (skill_id,))
        action_rows = cursor.fetchall()
        action_triggers = [row[0] for row in action_rows if row[0]]

        # Delete from agent_skill_map (Scoped to skill_id)
        cursor.execute("DELETE FROM agent_skill_map WHERE skill_id = ?", (skill_id,))

        # Delete from skill_registry (Scoped to skill_id)
        cursor.execute("DELETE FROM skill_registry WHERE skill_id = ?", (skill_id,))

        # Delete from route_registry (Scoped to this skill's action triggers)
        for trigger in action_triggers:
            cursor.execute("DELETE FROM route_registry WHERE action_trigger = ?", (trigger,))

        conn.commit()
        logger.info(f"[SERVICE] Safely unregistered skill_id='{skill_id}' from database.")