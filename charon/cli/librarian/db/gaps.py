"""
charon/cli/librarian/db/gaps.py
System Version: v0.2.0 | File Revision: 2.2.0

Module: Database queries and operations for gap tracking, quarantine metrics, and database purge maintenance.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.gaps")


def get_quarantined_orphans_count(db_path: Optional[Union[str, Path]] = None) -> int:
    """Queries count of quarantined/orphaned skills in charon_state.db."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return 0
    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_registry WHERE status = 'QUARANTINED'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query quarantined orphans count: {e}")
        return 0


def get_open_gaps_count(db_path: Optional[Union[str, Path]] = None) -> int:
    """Queries count of open skill gaps in charon_state.db."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return 0
    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'open'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query open gaps count: {e}")
        return 0


def get_resolved_gaps_count(db_path: Optional[Union[str, Path]] = None) -> int:
    """Queries count of resolved skill gaps pending database purge."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return 0
    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'resolved'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query resolved gaps count: {e}")
        return 0


def get_open_gaps(db_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """Fetches all open skill gaps as dictionaries from charon_state.db."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []
    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skill_gaps WHERE status = 'open'")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error querying skill_gaps table: {e}")
        return []


def resolve_gap_db(gap_id: int, db_path: Optional[Union[str, Path]] = None) -> bool:
    """Marks a specific skill gap as resolved in charon_state.db."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False
    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skill_gaps SET status = 'resolved', updated_at = CURRENT_TIMESTAMP WHERE gap_id = ?",
                (gap_id,),
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to resolve gap ID {gap_id} in database: {e}")
        return False


def purge_resolved_gaps_db(db_path: Optional[Union[str, Path]] = None) -> int:
    """Deletes all resolved gap records from the state database and returns row count."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        logger.info(f"[MAINTENANCE] Database file not found at {target_db}. Skipping purge.")
        return 0
    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM skill_gaps WHERE LOWER(status) = 'resolved'")
            purged_count = cursor.rowcount
            conn.commit()
            return purged_count
    except Exception as e:
        logger.error(f"Failed to purge resolved gaps from database: {e}")
        return 0


def vacuum_db(db_path: Optional[Union[str, Path]] = None) -> bool:
    """Runs a VACUUM command in autocommit mode to reclaim space and optimize the database."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False
    try:
        with get_connection(target_db) as conn:
            conn.isolation_level = None  # Enable autocommit for VACUUM
            conn.execute("VACUUM")
        return True
    except Exception as e:
        logger.warning(f"[MAINTENANCE] VACUUM execution failed: {e}")
        return False