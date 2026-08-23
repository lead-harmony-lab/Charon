"""
System Version: v2.0.0 | File Revision: 4.0.0

Module: CRUD operations and schema migrations for skill_registry and agent_skill_map.
Target Standard: Native domain and skill_type Schema Alignment.
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
    """Queries skill_registry for a specific skill_id using native domain and skill_type."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT skill_id, action_name, version, skill_type, domain, description,
                       parameters, system_requirements, consumed_artifacts,
                       produced_artifacts, entry_file_path, handler_name,
                       status, quarantine_reason, is_global, updated_at
                FROM skill_registry
                WHERE skill_id = ? OR LOWER(skill_id) = LOWER(?)
                """,
                (skill_id, skill_id),
            )
            row = cursor.fetchone()
            if row:
                stype = row[3] or "tool"
                dom = row[4] or "General"
                return {
                    "skill_id": row[0],
                    "action_name": row[1],
                    "version": row[2],
                    "skill_type": stype,
                    "domain": dom,
                    "category": f"{dom} / {stype.replace('_', ' ').title()}",
                    "description": row[5],
                    "parameters": json.loads(row[6]) if row[6] else {},
                    "system_requirements": json.loads(row[7]) if row[7] else [],
                    "consumed_artifacts": json.loads(row[8]) if row[8] else [],
                    "produced_artifacts": json.loads(row[9]) if row[9] else [],
                    "entry_file_path": row[10],
                    "handler_name": row[11],
                    "status": row[12],
                    "quarantine_reason": row[13],
                    "is_global": bool(row[14]),
                    "updated_at": row[15],
                }
    except Exception as e:
        logger.warning(f"Failed to query skill '{skill_id}' from DB: {e}")

    return None


def register_skill_in_db(
    skill_id: str,
    action_name: str,
    version: str,
    skill_type: str,
    domain: str,
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
    """Directly registers or updates a skill in skill_registry using domain and skill_type."""
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
                    skill_id, action_name, version, domain, skill_type, description,
                    parameters, system_requirements, consumed_artifacts, produced_artifacts,
                    entry_file_path, handler_name, status, quarantine_reason, is_global, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(skill_id) DO UPDATE SET
                    action_name = excluded.action_name,
                    version = excluded.version,
                    domain = excluded.domain,
                    skill_type = excluded.skill_type,
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
                    domain or "General",
                    skill_type or "tool",
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
    """Atomically renames a skill_id across skill_registry, agent_skill_map, and skill_permissions."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, f"Database file not found at {target_db}"

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = OFF;")

            cursor.execute(
                "SELECT entry_file_path FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)",
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
                WHERE LOWER(skill_id) = LOWER(?)
                """,
                (new_skill_id, new_path, old_skill_id),
            )

            cursor.execute(
                "UPDATE agent_skill_map SET skill_id = ? WHERE LOWER(skill_id) = LOWER(?)",
                (new_skill_id, old_skill_id),
            )

            cursor.execute(
                "UPDATE skill_permissions SET skill_id = ? WHERE LOWER(skill_id) = LOWER(?)",
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
    """Purges skill record and all FK dependencies across system_actions, routes, maps, and permissions."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return False

    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT action_name FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)",
                (skill_id,),
            )
            action_names = [row[0] for row in cursor.fetchall() if row[0]]

            for act in action_names:
                cursor.execute("DELETE FROM system_actions WHERE action_name = ?", (act,))
                cursor.execute("UPDATE agent_registry SET default_action = NULL WHERE default_action = ?", (act,))

            cursor.execute("DELETE FROM skill_permissions WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))
            cursor.execute("DELETE FROM agent_skill_map WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))
            cursor.execute("DELETE FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))

            conn.commit()
            logger.info(f"Purged database records and FK references scoped to skill_id='{skill_id}'")
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
                WHERE LOWER(skill_id) = LOWER(?)
            """, (skill_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to repair quarantined skill '{skill_id}': {e}")
        return False


def get_skill_inventory_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, str, Optional[str], Optional[str], Optional[str]]]:
    """Queries skill_registry joined with authorized agents for inventory display using native domain and skill_type."""
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
                    s.domain,
                    s.skill_type,
                    GROUP_CONCAT(DISTINCT asm.agent_id) AS agents
                FROM skill_registry s
                LEFT JOIN agent_skill_map asm ON s.skill_id = asm.skill_id
                GROUP BY s.skill_id, s.action_name, s.status, s.domain, s.skill_type
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
    skill_type: str,
    domain: str,
    global_description: str,
    sys_reqs: str,
    resolved_entry_path: str,
    initial_status: str,
    is_global: int,
    allowed_agents: List[str],
    target_agent_id: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> None:
    """Executes skill lifecycle registration in an atomic database transaction."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    with get_connection(target_db) as conn:
        cursor = conn.cursor()

        for action_def in actions_list:
            action_name = action_def.get("action_name")
            if not action_name:
                continue

            act_desc = action_def.get("description") or global_description or f"Executes '{action_name}'"
            handler_name = action_def.get("handler_name", f"handle_{action_name}")

            params = json.dumps(action_def.get("parameters", {}))
            consumed = json.dumps(action_def.get("consumed_artifacts", []))
            produced = json.dumps(action_def.get("produced_artifacts", []))

            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, domain, skill_type, description,
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, status, is_global
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    action_name=excluded.action_name,
                    version=excluded.version,
                    domain=excluded.domain,
                    skill_type=excluded.skill_type,
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
                    skill_id, action_name, version, domain or "General", skill_type or "tool", act_desc,
                    params, sys_reqs, consumed, produced,
                    resolved_entry_path, handler_name, initial_status, is_global,
                ),
            )

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
    """Safely unregisters a single skill and cleans up all FK dependencies from the database."""
    if not skill_id:
        logger.warning("[DB] Empty skill_id passed to unregister_skill_db. Aborting.")
        return

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return

    with get_connection(target_db) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT action_name FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))
        action_rows = cursor.fetchall()
        action_triggers = [row[0] for row in action_rows if row[0]]

        for trigger in action_triggers:
            cursor.execute("DELETE FROM system_actions WHERE action_name = ?", (trigger,))
            cursor.execute("UPDATE agent_registry SET default_action = NULL WHERE default_action = ?", (trigger,))

        cursor.execute("DELETE FROM skill_permissions WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))
        cursor.execute("DELETE FROM agent_skill_map WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))
        cursor.execute("DELETE FROM skill_registry WHERE LOWER(skill_id) = LOWER(?)", (skill_id,))

        conn.commit()