"""
charon/telemetry/ledger.py
System Version: v2.0.0

Module: Execution Audit Ledger
Append-only operational event logger recording role interactions,
tool executions, gatekeeper decisions, and engine state transitions.
Guarantees strict database separation using LEDGER_DB_PATH.
The BaseContractPolicy (which exposes a bind_telemetry method) and
the Coordinator should import the ledger from the telemetry package,
strictly decoupling I/O-bound logging from core state transitions.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.config.paths import LEDGER_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Telemetry.Ledger")


class ExecutionLedger:
    """Thread-safe, append-only operational event journal backed by SQLite WAL."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or LEDGER_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize append-only audit trail tables."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    role_name TEXT,
                    tool_name TEXT,
                    data_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ledger_task ON audit_ledger(task_id);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ledger_type ON audit_ledger(event_type);
                """
            )
        logger.info(f"ExecutionLedger initialized at: {self.db_path}")

    async def log_event(
        self,
        task_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        role_name: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> int:
        """Append an event entry to the audit log."""
        payload_str = json.dumps(data or {})

        def _exec() -> int:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO audit_ledger (task_id, event_type, role_name, tool_name, data_json)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (task_id, event_type, role_name, tool_name, payload_str),
                )
                return cursor.lastrowid or 0

        return await asyncio.to_thread(_exec)

    async def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve full chronological execution history for a task."""

        def _exec() -> List[Dict[str, Any]]:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, task_id, event_type, role_name, tool_name, data_json, timestamp
                    FROM audit_ledger
                    WHERE task_id = ?
                    ORDER BY id ASC;
                    """,
                    (task_id,),
                )
                results = []
                for row in cursor.fetchall():
                    item = dict(row)
                    try:
                        item["data"] = json.loads(item.pop("data_json") or "{}")
                    except json.JSONDecodeError:
                        item["data"] = {}
                    results.append(item)
                return results

        return await asyncio.to_thread(_exec)

    async def purge_task_history(self, task_id: str) -> int:
        """Purge audit history records for a specified task."""

        def _exec() -> int:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM audit_ledger WHERE task_id = ?;", (task_id,)
                )
                return cursor.rowcount

        return await asyncio.to_thread(_exec)