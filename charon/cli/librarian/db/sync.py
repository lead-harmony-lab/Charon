"""
System Version: v2.0.0 | File Revision: 3.5.0

Module: Filesystem re-indexing, plugin metadata querying, and orphan quarantine logic.
Target Standard: Manifest Schema V2 Only.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection
from .contracts import sync_system_actions

logger = logging.getLogger("charon.cli.librarian.db.sync")


def get_plugin_actions(
    manifest_path: str,
    entry_file_path: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, str]]:
    """Queries actions associated with a root plugin/manifest or entry path."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    actions: List[Dict[str, str]] = []

    if not target_db.exists():
        return actions

    extracted_skill_id: Optional[str] = None
    if manifest_path:
        m_path = Path(manifest_path)
        if m_path.exists():
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    extracted_skill_id = data.get("package") or data.get("skill_id")
            except Exception as e:
                logger.debug(f"Could not parse manifest at {manifest_path}: {e}")

        if not extracted_skill_id and m_path.parent:
            extracted_skill_id = m_path.parent.name

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT action_name, handler_name, description
                FROM skill_registry
                WHERE skill_id = ? OR (entry_file_path IS NOT NULL AND entry_file_path = ?)
                """,
                (extracted_skill_id or "", entry_file_path or ""),
            )
            for row in cursor.fetchall():
                actions.append(
                    {
                        "action_name": row[0] or "N/A",
                        "handler_name": row[1] or "N/A",
                        "description": row[2] or "",
                    }
                )
    except Exception as e:
        logger.warning(f"Failed to query plugin actions from DB: {e}")

    return actions


def flag_quarantined_orphans(db_path: Optional[Union[str, Path]] = None) -> int:
    """Quarantines skill records whose entry_file_path no longer exists on disk."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT skill_id, entry_file_path, status FROM skill_registry")
            rows = cursor.fetchall()

            flagged_count = 0
            for sid, entry_path_str, status in rows:
                if entry_path_str:
                    entry_path = Path(entry_path_str)
                    if not entry_path.exists() and (status or "").upper() != "QUARANTINED":
                        cursor.execute(
                            """
                            UPDATE skill_registry
                            SET status = 'QUARANTINED',
                                quarantine_reason = 'MISSING_ENTRY_FILE: Path on disk not found',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE skill_id = ?
                            """,
                            (sid,),
                        )
                        flagged_count += 1

            if flagged_count > 0:
                conn.commit()

        return flagged_count
    except Exception as e:
        logger.warning(f"Failed to flag quarantine orphans in SQLite: {e}")
        return 0


def run_sync(db_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Re-indexes filesystem manifests into SQLite, flags orphans, and syncs system actions.

    Returns:
        Dict[str, Any]: Re-indexing stats and operational state.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    from charon.core.skills import SkillLibrarian

    librarian = (
        SkillLibrarian.get_instance(db_path=target_db)
        if hasattr(SkillLibrarian.get_instance, "__code__")
        and "db_path" in SkillLibrarian.get_instance.__code__.co_varnames
        else SkillLibrarian.get_instance()
    )

    if hasattr(librarian, "reindex_skills"):
        librarian.reindex_skills()

    # Synchronize system action contracts registry with SQLite state
    contracts_synced, contracts_count, contract_msg = sync_system_actions(target_db)

    # Audit and flag missing entry files in SQLite quarantine
    flagged_orphans = flag_quarantined_orphans(target_db)

    registered_count = 0
    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM skill_registry")
                row = cursor.fetchone()
                registered_count = row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to fetch skill count from SQLite: {e}")

    return {
        "success": True,
        "registered_handlers": registered_count,
        "quarantined_orphans": flagged_orphans,
        "contracts_synced": contracts_synced,
        "contracts_count": contracts_count,
        "contracts_message": contract_msg,
    }