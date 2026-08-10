"""
charon/db/repositories/task.py
System Version: v0.6.0 | File Revision: 6.1.0

Module: Data Access Layer repository for managing task execution state records,
orchestration plans, step progress, and error tracking.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Task")


class TaskRepository:
    """The exclusive interface for managing task execution state records."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """
        Ensures task_state table and required indices exist.

        Note: Table creation is provided here for bootstrap initialization. Once the database schema
        stabilizes, DDL logic should be executed strictly through a dedicated system migration runner.
        """
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_state (
                    task_id TEXT PRIMARY KEY,
                    client_id TEXT,
                    prompt TEXT NOT NULL,
                    agent_override TEXT,
                    status TEXT NOT NULL,
                    current_step_index INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    plan_json TEXT,
                    results_json TEXT,
                    active_approval_id TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (agent_override) REFERENCES agent_registry(agent_id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_task_status ON task_state(status);
                CREATE INDEX IF NOT EXISTS idx_task_client ON task_state(client_id);
            """)

    def create_task(
        self,
        task_id: str,
        prompt: str,
        status: str,
        client_id: Optional[str] = None,
        agent_override: Optional[str] = None,
    ) -> None:
        """Inserts a new task execution record."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO task_state (task_id, client_id, prompt, agent_override, status)
                VALUES (?, ?, ?, ?, ?);
                """,
                (task_id, client_id, prompt, agent_override, status),
            )

    def update_status(
        self,
        task_id: str,
        status: str,
        error_message: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> None:
        """Updates task execution status and related error/approval state."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE task_state
                SET status = ?,
                    error_message = COALESCE(?, error_message),
                    active_approval_id = COALESCE(?, active_approval_id),
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?;
                """,
                (status, error_message, approval_id, task_id),
            )

    def save_plan(self, task_id: str, plan_str: str, total_steps: int) -> None:
        """Persists orchestration plan JSON."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE task_state
                SET plan_json = ?,
                    total_steps = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?;
                """,
                (plan_str, total_steps, task_id),
            )

    def update_step_progress(
        self, task_id: str, step_index: int, results_str: str
    ) -> None:
        """Updates current step progress and output payload."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE task_state
                SET current_step_index = ?,
                    results_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?;
                """,
                (step_index, results_str, task_id),
            )

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a task record dictionary by ID."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                "SELECT * FROM task_state WHERE task_id = ?;", (task_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_tasks_by_client(
        self, client_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetches task execution history for a given client utilizing idx_task_client."""
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                """
                SELECT * FROM task_state 
                WHERE client_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?;
                """,
                (client_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_unfinished_tasks(
        self, status_list: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetches unfinished tasks matching target status states for crash recovery."""
        placeholders = ", ".join("?" for _ in status_list)
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(
                f"SELECT * FROM task_state WHERE status IN ({placeholders});",
                tuple(status_list),
            )
            return [dict(row) for row in cursor.fetchall()]