"""
charon/cli/librarian/db/permissions.py
System Version: v0.2.0 | File Revision: 2.2.1

Module: Database access layer for RBAC permissions, agent defaults, and contract resolution.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.permissions")


def get_active_agent_ids(db_path: Optional[Union[str, Path]] = None) -> Set[str]:
    """Queries active agent_ids from agent_registry in charon_state.db."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return set()
    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT agent_id FROM agent_registry WHERE is_active = 1")
            return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.debug(f"Failed to query active agents from state DB: {e}")
        return set()


def resolve_skill_contract(
    cursor: sqlite3.Cursor, identifier: str
) -> Tuple[Optional[str], Optional[str]]:
    """Resolves identifier against skill_registry. Returns (action_name, skill_id)."""
    if not identifier:
        return (None, None)

    norm_id = identifier.replace("sk_", "").strip()

    # Exact match
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE action_name = ? OR skill_id = ? OR skill_id = ? OR action_name = ?
        """,
        (identifier, identifier, f"sk_{norm_id}", norm_id),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    # Path-based resolution
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE entry_file_path LIKE ? OR entry_file_path LIKE ?
           OR entry_file_path LIKE ? OR entry_file_path LIKE ?
        """,
        (f"%/{identifier}/%", f"%/{norm_id}/%", f"%\\{identifier}\\%", f"%\\{norm_id}\\%"),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    return (None, None)


def get_skill_permissions(db_path: Optional[Union[str, Path]] = None) -> Dict[str, Set[str]]:
    """Queries DB agent_skill_map to map authorized agent_ids to skill_ids and action_names."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    skill_map: Dict[str, Set[str]] = {}

    if not target_db.exists():
        return skill_map

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT asm.skill_id, asm.agent_id, sr.action_name
                FROM agent_skill_map asm
                LEFT JOIN skill_registry sr ON (asm.skill_id = sr.skill_id OR asm.skill_id = sr.action_name)
                """
            )
            for db_skill_id, agent_id, action_name in cursor.fetchall():
                if db_skill_id:
                    skill_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    skill_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    skill_map.setdefault(action_name, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query permissions from agent_skill_map: {e}")

    return skill_map


def get_skill_defaults(db_path: Optional[Union[str, Path]] = None) -> Dict[str, Set[str]]:
    """Queries state DB to map skill_ids and action_names to default agent bindings."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    default_map: Dict[str, Set[str]] = {}

    if not target_db.exists():
        return default_map

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.skill_id, s.action_name, a.agent_id, a.default_action
                FROM agent_registry a
                LEFT JOIN skill_registry s ON (a.default_action = s.action_name OR a.default_action = s.skill_id)
                WHERE a.is_active = 1 AND a.default_action IS NOT NULL
                """
            )
            for db_skill_id, action_name, agent_id, default_action in cursor.fetchall():
                if db_skill_id:
                    default_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    default_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    default_map.setdefault(action_name, set()).add(agent_id)
                if default_action:
                    default_map.setdefault(default_action, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query default action mappings: {e}")

    return default_map


def get_registered_agents(
    db_path: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Retrieves sorted list of registered agent identifiers, falling back to system defaults."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT agent_id FROM agent_registry ORDER BY agent_id ASC"
                )
                rows = cursor.fetchall()
                agents = [row[0] for row in rows if row[0]]
                if agents:
                    return agents
        except Exception as e:
            logger.warning(f"Failed to query registered agents: {e}")

    return ["executor", "coder", "researcher", "librarian"]


def grant_agent_permission_db(
    agent_id: str, skill_id: str, db_path: Optional[Union[str, Path]] = None
) -> Tuple[bool, str, list]:
    """Persists agent permission in agent_skill_map. Returns (success, msg/resolved_id, authorized_agents)."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not skill_id:
        return False, "Database or skill ID missing", []

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            _, target_sk_id = resolve_skill_contract(cursor, skill_id)
            if not target_sk_id:
                target_sk_id = skill_id

            cursor.execute("SELECT 1 FROM skill_registry WHERE skill_id = ?", (target_sk_id,))
            if not cursor.fetchone():
                msg = f"Skill '{target_sk_id}' is not yet indexed in skill_registry."
                logger.warning(msg)
                return False, msg, []

            cursor.execute("SELECT 1 FROM agent_registry WHERE agent_id = ?", (agent_id,))
            if not cursor.fetchone():
                return False, f"Agent '{agent_id}' not found in registry.", []

            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id) 
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, target_sk_id),
            )
            conn.commit()

            cursor.execute(
                "SELECT DISTINCT agent_id FROM agent_skill_map WHERE skill_id = ?",
                (target_sk_id,),
            )
            authorized_agents = sorted([row[0] for row in cursor.fetchall()])
            return True, target_sk_id, authorized_agents
    except Exception as e:
        logger.error(f"Failed to grant agent permission: {e}")
        return False, str(e), []


def revoke_agent_permission_db(
    agent_id: str, skill_id: str, db_path: Optional[Union[str, Path]] = None
) -> Tuple[bool, str, list]:
    """Revokes permission in agent_skill_map. Returns (success, msg/resolved_id, remaining_agents)."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not skill_id:
        return False, "Database or skill ID missing", []

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            _, matched_skill_id = resolve_skill_contract(cursor, skill_id)
            target_sk_id = matched_skill_id or skill_id
            norm_id = skill_id.replace("sk_", "")

            cursor.execute(
                """
                DELETE FROM agent_skill_map 
                WHERE agent_id = ? AND (skill_id = ? OR skill_id = ? OR skill_id = ?)
                """,
                (agent_id, skill_id, matched_skill_id or "", f"sk_{norm_id}"),
            )
            conn.commit()

            cursor.execute(
                "SELECT DISTINCT agent_id FROM agent_skill_map WHERE skill_id = ?",
                (target_sk_id,),
            )
            remaining_agents = sorted([row[0] for row in cursor.fetchall()])
            return True, target_sk_id, remaining_agents
    except Exception as e:
        logger.error(f"Failed to revoke agent permission: {e}")
        return False, str(e), []


def set_agent_default_skill_db(
    agent_id: str, action_name: str, db_path: Optional[Union[str, Path]] = None
) -> Tuple[bool, str, Optional[str]]:
    """Updates default_action in agent_registry AND propagates is_default flag to agent_skill_map."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, f"Database file not found at {target_db}", None

    try:
        warning_msg = None
        with get_connection(target_db) as conn:
            cursor = conn.cursor()

            # Resolve the action to a specific skill id and verify status
            cursor.execute(
                "SELECT skill_id, status FROM skill_registry WHERE action_name = ? OR skill_id = ? LIMIT 1",
                (action_name, action_name),
            )
            row = cursor.fetchone()
            if not row:
                return (
                    False,
                    f"Action/Skill '{action_name}' does not exist in skill_registry.",
                    None,
                )

            matched_skill_id, status = row

            if status != "ACTIVE":
                warning_msg = f"Action '{action_name}' belongs to skill '{matched_skill_id}' which has status '{status}'."

            # 1. Update Primary Contract in agent_registry
            cursor.execute(
                """
                UPDATE agent_registry
                SET default_action = ?, updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ?
                """,
                (action_name, agent_id),
            )

            if cursor.rowcount == 0:
                return False, f"Agent '{agent_id}' not found in agent_registry.", None

            # 2. Guarantee RBAC permission exists
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, matched_skill_id),
            )

            # 3. Propagate defaults to RBAC layer
            try:
                cursor.execute(
                    "UPDATE agent_skill_map SET is_default = 0 WHERE agent_id = ?",
                    (agent_id,),
                )
                cursor.execute(
                    """
                    UPDATE agent_skill_map SET is_default = 1 
                    WHERE agent_id = ? AND skill_id = ?
                    """,
                    (agent_id, matched_skill_id),
                )
            except sqlite3.OperationalError:
                pass

            conn.commit()
            return True, "", warning_msg
    except Exception as e:
        logger.error(f"Failed to set agent default skill: {e}")
        return False, f"Database error: {str(e)}", None


def update_agent_default_action(
    agent_id: str,
    action_name: Optional[str],
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Updates the default_action column for a given agent in the agent_registry table."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE agent_registry
                SET default_action = ?, updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ?
                """,
                (action_name, agent_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                logger.warning(
                    f"No agent record found with agent_id='{agent_id}' to update default_action."
                )
                return False
            return True
    except Exception as e:
        logger.error(f"Failed to update default action for agent '{agent_id}': {e}")
        return False