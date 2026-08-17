"""
System Version: v2.0.0 | File Revision: 1.0.0

Module: CRUD operations and contract policy lookups for CBAC (Capability-Based Access Control).
Target Standard: WorkContract schema alignment and governance envelope persistence.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.cbac")


def get_contract_by_id(
    contract_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """Queries work_contracts and retrieves full governance policy and scope limits."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_id, contract_name, agent_id, skill_id,
                       scope_limits, rate_limit_rpm, token_boundary,
                       is_active, updated_at
                FROM work_contracts
                WHERE contract_id = ? OR LOWER(contract_id) = LOWER(?)
                """,
                (contract_id, contract_id),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "contract_id": row[0],
                    "contract_name": row[1],
                    "agent_id": row[2],
                    "skill_id": row[3],
                    "scope_limits": json.loads(row[4]) if row[4] else {},
                    "rate_limit_rpm": row[5],
                    "token_boundary": row[6],
                    "is_active": bool(row[7]),
                    "updated_at": row[8],
                }
    except Exception as e:
        logger.warning(f"Failed to query contract '{contract_id}' from DB: {e}")

    return None


def register_contract_in_db(
    contract_id: str,
    contract_name: str,
    agent_id: str,
    skill_id: str,
    scope_limits: Optional[Dict[str, Any]] = None,
    rate_limit_rpm: Optional[int] = 60,
    token_boundary: Optional[int] = 4096,
    is_active: bool = True,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """Registers or updates a CBAC WorkContract governance policy in the database."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    scope_str = json.dumps(scope_limits or {})

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO work_contracts (
                    contract_id, contract_name, agent_id, skill_id,
                    scope_limits, rate_limit_rpm, token_boundary,
                    is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(contract_id) DO UPDATE SET
                    contract_name = excluded.contract_name,
                    agent_id = excluded.agent_id,
                    skill_id = excluded.skill_id,
                    scope_limits = excluded.scope_limits,
                    rate_limit_rpm = excluded.rate_limit_rpm,
                    token_boundary = excluded.token_boundary,
                    is_active = excluded.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    contract_id,
                    contract_name,
                    agent_id,
                    skill_id,
                    scope_str,
                    rate_limit_rpm,
                    token_boundary,
                    1 if is_active else 0,
                ),
            )
            conn.commit()
        return True, ""
    except Exception as e:
        return False, f"Contract Registration Error: {str(e)}"


def get_contract_inventory_db(
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, str, str, str, bool, Optional[int], Optional[int]]]:
    """Queries work_contracts for inventory displays in the CBAC control panel."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    contract_id,
                    contract_name,
                    agent_id,
                    skill_id,
                    is_active,
                    rate_limit_rpm,
                    token_boundary
                FROM work_contracts
                ORDER BY contract_id ASC
                """
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to fetch CBAC contract inventory from DB: {e}")
        return []


def toggle_contract_status_db(
    contract_id: str,
    is_active: bool,
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Enables or disables an active WorkContract policy."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not contract_id:
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE work_contracts
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(contract_id) = LOWER(?)
                """,
                (1 if is_active else 0, contract_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.warning(f"Failed to toggle status for contract '{contract_id}': {e}")
        return False


def purge_contract_records(
    contract_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Deletes a WorkContract policy record from the database."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists() or not contract_id:
        return False

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM work_contracts WHERE LOWER(contract_id) = LOWER(?)",
                (contract_id,),
            )
            conn.commit()
            return True
    except Exception as e:
        logger.warning(f"Failed to purge contract '{contract_id}': {e}")
        return False