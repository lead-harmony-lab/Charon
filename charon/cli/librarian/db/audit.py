"""
charon/cli/librarian/db/audit.py
System Version: v0.2.0 | File Revision: 2.2.0

Module: Database vs. filesystem state drift inspection (Pure Data Queries).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.db.audit")


def _audit_agent_skill_map(conn) -> List[Tuple[str, str]]:
    """Identifies orphaned records in agent_skill_map referencing missing skill_ids."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_skill_map'"
    )
    if not cursor.fetchone():
        return []

    cursor.execute("""
        SELECT asm.agent_id, asm.skill_id
        FROM agent_skill_map asm
        LEFT JOIN skill_registry sr ON asm.skill_id = sr.skill_id
        WHERE sr.skill_id IS NULL
    """)
    return cursor.fetchall()


def perform_state_audit(
    db_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Audits SQLite registry state against disk manifests and agent_skill_map integrity.

    Returns:
        Dict[str, Any]: Contains 'skills' comparison list, 'orphaned_mappings', and total 'drift_count'.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    db_skill_action_counts: Dict[str, int] = {}
    orphaned_mappings: List[Tuple[str, str]] = []

    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_registry'"
                )
                if cursor.fetchone():
                    cursor.execute(
                        "SELECT skill_id, COUNT(action_name) FROM skill_registry GROUP BY skill_id"
                    )
                    for row in cursor.fetchall():
                        db_skill_action_counts[row[0]] = row[1]

                orphaned_mappings = _audit_agent_skill_map(conn)

        except Exception as e:
            logger.error(f"Failed to query SQLite state during audit: {e}")
            return {
                "error": str(e),
                "skills": [],
                "orphaned_mappings": [],
                "drift_count": 1,
            }

    disk_manifests: Dict[str, Dict[str, Any]] = {}
    search_dirs = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    for root in search_dirs:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sid = data.get("skill_id")
                    if sid:
                        category = data.get("category", "General")
                        actions = data.get("supported_actions", {})
                        action_count = (
                            len(actions) if isinstance(actions, dict) else 0
                        )

                        disk_manifests[sid] = {
                            "path": manifest_path,
                            "category": category,
                            "disk_action_count": action_count,
                        }
            except Exception as e:
                logger.warning(
                    f"Failed to read manifest at {manifest_path}: {e}"
                )
                continue

    audited_skills = []
    drift_count = 0

    for sid, meta in disk_manifests.items():
        disk_count = meta["disk_action_count"]
        db_count = db_skill_action_counts.get(sid, 0)

        if db_count == 0:
            status = "UNINDEXED"
            drift_count += 1
        elif db_count < disk_count:
            status = "PARTIAL"
            drift_count += 1
        else:
            status = "IN_SYNC"

        audited_skills.append({
            "skill_id": sid,
            "category": meta["category"],
            "disk_count": disk_count,
            "db_count": db_count,
            "status": status,
            "missing_actions": max(0, disk_count - db_count),
        })

    drift_count += len(orphaned_mappings)

    return {
        "skills": audited_skills,
        "orphaned_mappings": orphaned_mappings,
        "drift_count": drift_count,
    }


def cleanup_orphaned_agent_mappings_db(
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """Purges orphaned records from agent_skill_map where skill_id no longer exists in skill_registry."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return 0

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_skill_map'"
            )
            if not cursor.fetchone():
                return 0

            cursor.execute("""
                SELECT DISTINCT skill_id 
                FROM agent_skill_map 
                WHERE skill_id NOT IN (SELECT skill_id FROM skill_registry)
            """)
            orphans = cursor.fetchall()
            if not orphans:
                return 0

            cursor.execute("""
                DELETE FROM agent_skill_map
                WHERE skill_id NOT IN (SELECT skill_id FROM skill_registry)
            """)
            conn.commit()
            purged_count = len(orphans)
            logger.info(
                f"Purged {purged_count} orphaned records from agent_skill_map."
            )
            return purged_count
    except Exception as e:
        logger.warning(f"Failed to cleanup orphaned agent mappings: {e}")
        return 0