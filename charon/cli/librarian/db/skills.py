"""
charon/cli/librarian/db/skills.py
System Version: v0.2.0 | File Revision: 2.3.0

Module: CRUD operations and schema migrations for skill_registry and agent_skill_map.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection
from .utils import _slugify

logger = logging.getLogger("charon.cli.librarian.db.skills")


def get_skill_by_id(
    skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Queries skill_registry for a specific skill_id."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT skill_id, action_name, version, category, description,
                       parameters, system_requirements, consumed_artifacts,
                       produced_artifacts, entry_file_path, handler_name,
                       status, quarantine_reason, is_global, updated_at
                FROM skill_registry
                WHERE skill_id = ?
                """,
                (skill_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "skill_id": row[0],
                    "action_name": row[1],
                    "version": row[2],
                    "category": row[3],
                    "description": row[4],
                    "parameters": json.loads(row[5]) if row[5] else {},
                    "system_requirements": json.loads(row[6]) if row[6] else [],
                    "consumed_artifacts": json.loads(row[7]) if row[7] else [],
                    "produced_artifacts": json.loads(row[8]) if row[8] else [],
                    "entry_file_path": row[9],
                    "handler_name": row[10],
                    "status": row[11],
                    "quarantine_reason": row[12],
                    "is_global": bool(row[13]),
                    "updated_at": row[14],
                }
    except Exception as e:
        logger.warning(f"Failed to query skill '{skill_id}' from DB: {e}")

    return None


def register_skill_in_db(
    skill_id: str,
    action_name: str,
    version: str,
    category: str,
    description: str,
    parameters: dict,
    system_requirements: list,
    consumed_artifacts: list,
    produced_artifacts: list,
    entry_file_path: Path,
    handler_name: str = "execute_action",
    is_global: int = 0,
    status: str = "STAGED",
    quarantine_reason: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Directly registers or updates a skill in skill_registry."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    abs_entry_path = str(entry_file_path.resolve())

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT skill_id FROM skill_registry WHERE action_name = ? AND skill_id != ?",
                (action_name, skill_id),
            )
            collision = cursor.fetchone()
            if collision:
                return False, f"Action name collision: '{action_name}' is already assigned to skill '{collision[0]}'."

            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, category, description,
                    parameters, system_requirements, consumed_artifacts, produced_artifacts,
                    entry_file_path, handler_name, status, quarantine_reason, is_global, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(skill_id, action_name) DO UPDATE SET
                    version = excluded.version,
                    category = excluded.category,
                    description = excluded.description,
                    parameters = excluded.parameters,
                    system_requirements = excluded.system_requirements,
                    consumed_artifacts = excluded.consumed_artifacts,
                    produced_artifacts = excluded.produced_artifacts,
                    entry_file_path = excluded.entry_file_path,
                    handler_name = excluded.handler_name,
                    status = excluded.status,
                    quarantine_reason = excluded.quarantine_reason,
                    is_global = excluded.is_global,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    skill_id,
                    action_name,
                    version,
                    category,
                    description,
                    json.dumps(parameters),
                    json.dumps(system_requirements),
                    json.dumps(consumed_artifacts),
                    json.dumps(produced_artifacts),
                    abs_entry_path,
                    handler_name,
                    status,
                    quarantine_reason,
                    is_global,
                ),
            )
            conn.commit()
        return True, ""
    except Exception as e:
        return False, f"Database Registration Error: {str(e)}"


def migrate_skill_id_in_db(
    old_skill_id: str,
    new_skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Atomically renames a skill_id across skill_registry and agent_skill_map."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, f"Database file not found at {target_db}"

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF;")

            cursor.execute(
                "SELECT entry_file_path FROM skill_registry WHERE skill_id = ?",
                (old_skill_id,),
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute("PRAGMA foreign_keys = ON;")
                return False, f"Record '{old_skill_id}' not found in skill_registry."

            old_path = row[0] or ""
            new_path = old_path.replace(old_skill_id, new_skill_id)

            cursor.execute(
                """
                UPDATE skill_registry
                SET skill_id = ?, entry_file_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE skill_id = ?
                """,
                (new_skill_id, new_path, old_skill_id),
            )

            cursor.execute(
                "UPDATE agent_skill_map SET skill_id = ? WHERE skill_id = ?",
                (new_skill_id, old_skill_id),
            )

            conn.commit()
            cursor.execute("PRAGMA foreign_keys = ON;")

        return True, f"Migrated '{old_skill_id}' -> '{new_skill_id}' across SQLite tables."
    except Exception as e:
        logger.error(f"Failed to migrate skill ID in DB: {e}")
        return False, f"Database error during migration: {str(e)}"


def get_skill_entry_and_status(skill_id: str) -> List[Tuple[Optional[str], Optional[str]]]:
    """Queries skill_registry for entry_file_path and status for a given skill_id."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return []

    clean_id = _slugify(skill_id)
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT entry_file_path, status
                FROM skill_registry
                WHERE skill_id = ? OR LOWER(skill_id) = LOWER(?) OR LOWER(skill_id) = LOWER(?)
                """,
                (skill_id, skill_id, clean_id),
            )
            return cursor.fetchall()
    except Exception as e:
        logger.debug(f"DB lookup failed in get_skill_entry_and_status: {e}")
        return []


def purge_skill_records(skill_id: str) -> bool:
    """Purges corresponding bindings from agent_skill_map and skill_registry."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return False

    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM agent_skill_map WHERE LOWER(skill_id) = LOWER(?)",
                (skill_id,),
            )
            cursor.execute(
                "DELETE FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)",
                (skill_id,),
            )
            conn.commit()
            logger.info(f"Purged database records scoped strictly to skill_id='{skill_id}'")
            return True
    except Exception as e:
        logger.warning(f"Failed to purge DB records for skill '{skill_id}': {e}")
        return False


def get_deficient_skills_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, str, str]]:
    """Retrieves skill records missing parameters or artifacts."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_id, action_name, handler_name, entry_file_path 
                FROM skill_registry
                WHERE parameters = '{}' 
                   OR consumed_artifacts = '[]' 
                   OR produced_artifacts = '[]'
            """)
            return cursor.fetchall()
    except Exception as e:
        logger.warning(f"Failed to query deficient skills from DB: {e}")
        return []


def get_quarantined_skills_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, Optional[str]]]:
    """Fetches list of currently quarantined skill entries."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_id, entry_file_path, quarantine_reason 
                FROM skill_registry 
                WHERE status = 'QUARANTINED'
            """)
            return cursor.fetchall()
    except Exception as e:
        logger.warning(f"Failed to query quarantined skills from DB: {e}")
        return []


def repair_quarantined_skill_db(
    skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Reactivates a quarantined skill record in the database."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not skill_id:
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE skill_registry 
                SET status = 'ACTIVE', quarantine_reason = NULL, updated_at = CURRENT_TIMESTAMP 
                WHERE skill_id = ?
            """, (skill_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to repair quarantined skill '{skill_id}': {e}")
        return False


def get_skill_inventory_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, str, Optional[str], Optional[str]]]:
    """Queries skill_registry joined with authorized agents for inventory display."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    s.skill_id,
                    s.action_name,
                    s.status,
                    s.category,
                    GROUP_CONCAT(DISTINCT asm.agent_id) AS agents
                FROM skill_registry s
                LEFT JOIN agent_skill_map asm ON s.skill_id = asm.skill_id
                GROUP BY s.skill_id, s.action_name, s.status, s.category
                ORDER BY s.skill_id ASC, s.action_name ASC
                """
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch skill inventory from DB: {e}")
        return []


def register_and_bind_skill_db(
    skill_id: str,
    actions_list: List[Dict[str, Any]],
    version: str,
    category: str,
    global_description: str,
    sys_reqs: str,
    resolved_entry_path: str,
    initial_status: str,
    is_global: int,
    allowed_agents: List[str],
    target_agent_id: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """
    Executes skill lifecycle registration in an atomic database transaction:
      1. UPSERT into skill_registry (Keyed on skill_id, action_name)
      2. UPSERT into route_registry (Action trigger <-> system_roles)
      3. INSERT into agent_skill_map (Relational authorization: agent_id <-> skill_id)
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    with get_connection(target_db) as conn:
        cursor = conn.cursor()

        # -----------------------------------------------------------------
        # STEP 1: skill_registry & route_registry
        # -----------------------------------------------------------------
        for action_def in actions_list:
            action_name = action_def.get("action_name")
            if not action_name:
                continue

            act_desc = action_def.get("description") or global_description or f"Executes '{action_name}'"
            handler_name = action_def.get("handler_name", f"handle_{action_name}")

            # Extract action-level JSON metadata
            params = json.dumps(action_def.get("parameters", {}))
            consumed = json.dumps(action_def.get("consumed_artifacts", []))
            produced = json.dumps(action_def.get("produced_artifacts", []))

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
                    skill_id, action_name, version, category, act_desc,
                    params, sys_reqs, consumed, produced,
                    resolved_entry_path, handler_name, initial_status, is_global,
                ),
            )

            # Route resolution
            target_role = None
            if target_agent_id:
                # Safely strip "role:" prefix for DB lookups
                sanitized_target = target_agent_id.replace("role:", "")
                cursor.execute(
                    "SELECT role_name FROM system_roles WHERE role_name = ? OR agent_id = ?",
                    (sanitized_target, sanitized_target),
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
        # STEP 2: agent_skill_map bindings (CBAC)
        # -----------------------------------------------------------------
        if target_agent_id:
            sanitized_target = target_agent_id.replace("role:", "")
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                SELECT agent_id, ? FROM agent_registry WHERE (agent_id = ? OR default_action = ?) AND is_active = 1
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (skill_id, sanitized_target, sanitized_target),
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
            for agent_role in allowed_agents:
                if agent_role and agent_role != "*":
                    sanitized_role = agent_role.replace("role:", "")
                    cursor.execute(
                        """
                        INSERT INTO agent_skill_map (agent_id, skill_id)
                        SELECT agent_id, ? FROM agent_registry WHERE (agent_id = ? OR default_action = ?) AND is_active = 1
                        ON CONFLICT(agent_id, skill_id) DO NOTHING
                        """,
                        (skill_id, sanitized_role, sanitized_role),
                    )

        conn.commit()


def unregister_skill_db(
    skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
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
        logger.warning("[DB] Empty skill_id passed to unregister_skill_db. Aborting.")
        return

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return

    with get_connection(target_db) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT action_name FROM skill_registry WHERE skill_id = ?", (skill_id,))
        action_rows = cursor.fetchall()
        action_triggers = [row[0] for row in action_rows if row[0]]

        cursor.execute("DELETE FROM agent_skill_map WHERE skill_id = ?", (skill_id,))
        cursor.execute("DELETE FROM skill_registry WHERE skill_id = ?", (skill_id,))

        for trigger in action_triggers:
            cursor.execute("DELETE FROM route_registry WHERE action_trigger = ?", (trigger,))

        conn.commit()