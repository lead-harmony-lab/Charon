"""
charon/db/repositories/gap.py
System Version: v0.6.0 | File Revision: 5.1.0

Module: Data Access Layer repository for logging, tracking, and resolving skill gaps.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Gap")


class SkillGapRepository:
    """Data access layer for tracking and resolving missing skill gaps."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """Initializes the skill_gaps database table and indices if they do not exist."""
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skill_gaps (
                    gap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_name TEXT NOT NULL,
                    requesting_agent TEXT NOT NULL,
                    missing_prerequisites TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (requesting_agent) REFERENCES agent_registry(agent_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_skill_gaps_status ON skill_gaps(status);
                CREATE INDEX IF NOT EXISTS idx_skill_gaps_agent ON skill_gaps(requesting_agent);
            """)

    def get_open_gaps(self) -> List[Dict[str, Any]]:
        """Fetch all open skill gaps from the state database."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                """
                SELECT gap_id, action_name, requesting_agent, missing_prerequisites, status, created_at
                FROM skill_gaps
                WHERE status = 'open'
                ORDER BY created_at ASC;
                """
            )
            rows = cursor.fetchall()

            gaps = []
            for row in rows:
                row_dict = dict(row)
                prereqs = row_dict.get("missing_prerequisites")
                try:
                    row_dict["missing_prerequisites"] = json.loads(prereqs) if prereqs else []
                except (json.JSONDecodeError, TypeError):
                    row_dict["missing_prerequisites"] = []
                gaps.append(row_dict)

            return gaps

    def resolve_gap(self, gap_id: int) -> bool:
        """Marks a skill gap as resolved."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE skill_gaps
                SET status = 'resolved', updated_at = CURRENT_TIMESTAMP
                WHERE gap_id = ?;
                """,
                (gap_id,),
            )
            return cursor.rowcount > 0

    def log_skill_gap(
        self,
        action_name: str,
        agent_name: Optional[str] = None,
        missing_prereqs: Optional[List[Any]] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Records identified skill gaps into the state database.
        Safely resolves agent targets to prevent SQLite FK constraint errors.
        """
        target_agent = agent_id or agent_name or "unknown"
        prereqs = missing_prereqs if missing_prereqs is not None else []

        with get_connection(self.db_path, row_factory=True) as conn:
            # 1. Verify target_agent exists in agent_registry
            cursor = conn.execute(
                "SELECT agent_id FROM agent_registry WHERE agent_id = ? LIMIT 1;",
                (target_agent,),
            )
            resolved = cursor.fetchone()

            # 2. Check if target_agent is an abstract system role
            if not resolved:
                cursor = conn.execute(
                    "SELECT agent_id FROM system_roles WHERE role_name = ? AND agent_id IS NOT NULL LIMIT 1;",
                    (target_agent,),
                )
                role_row = cursor.fetchone()
                if role_row:
                    target_agent = str(role_row["agent_id"])
                    resolved = True

            # 3. Fallback to active default agent if unresolved
            if not resolved:
                cursor = conn.execute(
                    "SELECT agent_id FROM agent_registry WHERE is_active = 1 ORDER BY rowid ASC LIMIT 1;"
                )
                fallback = cursor.fetchone()
                if fallback:
                    target_agent = str(fallback["agent_id"])
                else:
                    logger.warning(
                        f"[SkillGapRepository] Cannot log gap '{action_name}': no active agents in agent_registry."
                    )
                    return

            conn.execute(
                """
                INSERT INTO skill_gaps (action_name, requesting_agent, missing_prerequisites, status)
                VALUES (?, ?, ?, 'open');
                """,
                (action_name, target_agent, json.dumps(prereqs)),
            )
        logger.info(f"[SkillGapRepository] Logged skill gap '{action_name}' for agent '{target_agent}'.")