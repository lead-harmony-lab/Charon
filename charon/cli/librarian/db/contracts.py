"""
charon/cli/librarian/db/contracts.py
System Version: v0.2.0 | File Revision: 2.2.0

Module: Database vs. filesystem state drift inspection (Pure Data Queries).
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH, SYSTEM_ACTIONS_JSON
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.contracts")


def get_system_action_contract(
    action_name: Optional[str],
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Queries system_actions table to check contract compliance."""
    if not action_name or action_name == "N/A":
        return None

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT reserved_key, required_role, is_mandatory, description
                FROM system_actions
                WHERE action_name = ?
                """,
                (action_name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "reserved_key": row[0],
                    "required_role": row[1],
                    "is_mandatory": bool(row[2]),
                    "description": row[3] or "",
                }
    except sqlite3.Error as e:
        logger.debug(f"Failed to query system action contract for '{action_name}': {e}")
    except Exception as e:
        logger.warning(f"Unexpected error querying system_actions table: {e}")

    return None


def sync_system_actions(db_path: Optional[Union[str, Path]] = None) -> Tuple[bool, int, str]:
    """Synchronizes system_actions.json foundational blueprint into SQLite.

    Returns:
        Tuple[bool, int, str]: (success, synced_record_count, message)
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not SYSTEM_ACTIONS_JSON.exists():
        return False, 0, f"File not found: {SYSTEM_ACTIONS_JSON}"

    try:
        with open(SYSTEM_ACTIONS_JSON, "r", encoding="utf-8") as f:
            actions_manifest = json.load(f)

        synced_count = 0
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            for action in actions_manifest:
                cursor.execute(
                    """
                    INSERT INTO system_actions (
                        reserved_key, action_name, required_role, is_mandatory, description
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(reserved_key) DO UPDATE SET
                        action_name = excluded.action_name,
                        required_role = excluded.required_role,
                        is_mandatory = excluded.is_mandatory,
                        description = excluded.description,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        action.get("reserved_key"),
                        action.get("action_name"),
                        action.get("required_role"),
                        action.get("is_mandatory", 1),
                        action.get("description", ""),
                    ),
                )
                synced_count += 1
            conn.commit()
        return True, synced_count, "System actions blueprint synced successfully."
    except Exception as e:
        logger.error(f"Failed to sync system_actions.json: {e}")
        return False, 0, str(e)


def get_available_system_contracts(
    agent_roles: List[str],
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[Any, ...]]:
    """Queries system_actions for contracts matching agent roles."""
    if not agent_roles:
        return []

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in agent_roles)
            cursor.execute(
                f"""
                SELECT reserved_key, required_role, action_name, description, is_mandatory
                FROM system_actions
                WHERE required_role IN ({placeholders})
                """,
                tuple(agent_roles),
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to query system_actions for roles {agent_roles}: {e}")
        return []


def bind_system_action_to_contract(
    skill_action_name: str,
    target_reserved_key: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Binds a skill action_name to a system role contract."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, "Database not found."

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE system_actions
                SET action_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE reserved_key = ?
                """,
                (skill_action_name, target_reserved_key),
            )
            conn.commit()
        return True, f"Successfully bound system contract '{target_reserved_key}' to action '{skill_action_name}'."
    except Exception as e:
        logger.error(f"Failed to bind system action '{skill_action_name}' to '{target_reserved_key}': {e}")
        return False, f"Database error: {str(e)}"