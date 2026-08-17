"""
System Version: v2.0.0 | File Revision: 1.0.0

Module: CRUD operations and state management for agent_registry and system_roles.
Target Standard: Native JSON-to-SQLite Agent Sync alignment.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.agents")


def get_agent_by_id(
    agent_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Queries agent_registry and joins role information for a specific agent_id."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.agent_id, a.agent_name, a.description, a.default_action,
                       a.is_active, a.config_json, a.updated_at, r.role_name
                FROM agent_registry a
                LEFT JOIN system_roles r ON a.agent_id = r.agent_id
                WHERE a.agent_id = ? OR LOWER(a.agent_id) = LOWER(?)
                """,
                (agent_id, agent_id),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "agent_id": row[0],
                    "agent_name": row[1],
                    "description": row[2],
                    "default_action": row[3],
                    "is_active": bool(row[4]),
                    "config": json.loads(row[5]) if row[5] else {},
                    "updated_at": row[6],
                    "role_name": row[7],
                }
    except Exception as e:
        logger.warning(f"Failed to query agent '{agent_id}' from DB: {e}")

    return None


def register_agent_in_db(
    agent_id: str,
    agent_name: str,
    description: str,
    default_action: Optional[str] = None,
    role_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    is_active: bool = True,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Registers or updates an agent record in agent_registry and updates role mapping."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    config_str = json.dumps(config or {})

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO agent_registry (
                    agent_id, agent_name, description, default_action,
                    is_active, config_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id) DO UPDATE SET
                    agent_name = excluded.agent_name,
                    description = excluded.description,
                    default_action = excluded.default_action,
                    is_active = excluded.is_active,
                    config_json = excluded.config_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    agent_id,
                    agent_name,
                    description,
                    default_action,
                    1 if is_active else 0,
                    config_str,
                ),
            )

            if role_name:
                cursor.execute(
                    """
                    INSERT INTO system_roles (role_name, agent_id, description)
                    VALUES (?, ?, ?)
                    ON CONFLICT(role_name) DO UPDATE SET
                        agent_id = excluded.agent_id,
                        description = excluded.description
                    """,
                    (role_name, agent_id, f"Role mapping for {agent_name}"),
                )

            conn.commit()
        return True, ""
    except Exception as e:
        return False, f"Agent Registration Error: {str(e)}"


def get_agent_inventory_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, bool, Optional[str], Optional[str], int]]:
    """Queries agent_registry joined with bound skill counts for inventory views."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    a.agent_id,
                    a.agent_name,
                    a.is_active,
                    a.default_action,
                    r.role_name,
                    COUNT(asm.skill_id) AS bound_skills
                FROM agent_registry a
                LEFT JOIN system_roles r ON a.agent_id = r.agent_id
                LEFT JOIN agent_skill_map asm ON a.agent_id = asm.agent_id
                GROUP BY a.agent_id, a.agent_name, a.is_active, a.default_action, r.role_name
                ORDER BY a.agent_id ASC
                """
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch agent inventory from DB: {e}")
        return []


def toggle_agent_status_db(
    agent_id: str,
    is_active: bool,
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Activates or deactivates an agent in the registry."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not agent_id:
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE agent_registry
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(agent_id) = LOWER(?)
                """,
                (1 if is_active else 0, agent_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to toggle status for agent '{agent_id}': {e}")
        return False


def purge_agent_records(
    agent_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Purges agent record and cleans up associated roles and skill mappings."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not agent_id:
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM system_roles WHERE LOWER(agent_id) = LOWER(?)", (agent_id,))
            cursor.execute("DELETE FROM agent_skill_map WHERE LOWER(agent_id) = LOWER(?)", (agent_id,))
            cursor.execute("DELETE FROM agent_registry WHERE LOWER(agent_id) = LOWER(?)", (agent_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.warning(f"Failed to purge agent records for '{agent_id}': {e}")
        return False