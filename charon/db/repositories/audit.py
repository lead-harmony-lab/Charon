"""
charon/db/repositories/audit.py
System Version: v0.6.0 | File Revision: 1.1.0

Module: Data Access Layer repository for Overseer automated action and audit logging.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Audit")


class AuditRepository:
    """Repository for Overseer automated action, security, and quarantine logging."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """Initializes the overseer_audit_log table if not present."""
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS overseer_audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    target_entity TEXT NOT NULL,
                    details TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def log_overseer_action(self, action_type: str, target_entity: str, details: Dict[str, Any]) -> bool:
        """Logs an automated maintenance or recovery action executed by Overseer."""
        self.ensure_schema()
        query = """
            INSERT INTO overseer_audit_log (action_type, target_entity, details)
            VALUES (?, ?, ?);
        """
        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(query, (action_type, target_entity, json.dumps(details)))
                return cursor.rowcount > 0
        except Exception as err:
            logger.error(f"[AuditRepository] Failed to log Overseer action: {err}", exc_info=True)
            return False