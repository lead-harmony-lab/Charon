"""
charon/db/repositories/ticker.py
System Version: v0.6.0 | File Revision: 6.1.0

Module: Data Access Layer repository for managing the idle notification ticker feed,
desktop interaction alerts, and Overseer event feeds.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Ticker")


class TickerRepository:
    """The exclusive interface for managing the idle notification ticker feed and interactive desktop alerts."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """
        Ensures idle_ticker_feed table and interactive schema indices exist.

        Note: Table creation is provided here for bootstrap initialization. Once the database schema
        stabilizes, DDL logic should be executed strictly through a dedicated system migration runner.
        """
        with get_connection(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS idle_ticker_feed (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'SYSTEM',
                    urgency TEXT NOT NULL DEFAULT 'NORMAL' CHECK(urgency IN ('CRITICAL', 'NORMAL', 'LOW')),
                    message TEXT NOT NULL,
                    action_type TEXT DEFAULT NULL,
                    action_payload TEXT DEFAULT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT DEFAULT NULL,
                    dismissed INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_ticker_active ON idle_ticker_feed(dismissed, expires_at);
                CREATE INDEX IF NOT EXISTS idx_ticker_urgency ON idle_ticker_feed(urgency);
                CREATE INDEX IF NOT EXISTS idx_ticker_created ON idle_ticker_feed(created_at DESC);
            """)

    # =========================================================================
    # 1. WRITE & ALERT POSTING OPERATIONS
    # =========================================================================

    def add_ticker_item(
        self,
        item_id: str,
        message: str,
        category: str = "SYSTEM",
        urgency: str = "NORMAL",
        action_type: Optional[str] = None,
        action_payload: Optional[Dict[str, Any]] = None,
        created_at_iso: Optional[str] = None,
        expires_at_iso: Optional[str] = None,
    ) -> bool:
        """
        Inserts or refreshes a ticker notification item with optional interactive payload.
        """
        created_at = created_at_iso or datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(action_payload) if action_payload is not None else None

        query = """
            INSERT INTO idle_ticker_feed (
                id, category, urgency, message, action_type, action_payload, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                category = EXCLUDED.category,
                urgency = EXCLUDED.urgency,
                message = EXCLUDED.message,
                action_type = EXCLUDED.action_type,
                action_payload = EXCLUDED.action_payload,
                expires_at = EXCLUDED.expires_at,
                dismissed = 0;
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                query,
                (
                    item_id,
                    category,
                    urgency.upper(),
                    message,
                    action_type,
                    payload_json,
                    created_at,
                    expires_at_iso,
                ),
            )
            success = cursor.rowcount > 0

        if success:
            logger.info("Added/updated ticker item '%s' [%s | %s].", item_id, category, urgency)
        return success

    def post_alert(
        self,
        feed_id: str,
        message: str,
        urgency: str = "NORMAL",
        category: str = "SYSTEM",
        action_type: Optional[str] = None,
        action_payload: Optional[Dict[str, Any]] = None,
        expires_at_iso: Optional[str] = None,
    ) -> bool:
        """Convenience alias for post_alert to support system-level event creation."""
        return self.add_ticker_item(
            item_id=feed_id,
            message=message,
            category=category,
            urgency=urgency,
            action_type=action_type,
            action_payload=action_payload,
            expires_at_iso=expires_at_iso,
        )

    # =========================================================================
    # 2. READ & QUERY OPERATIONS
    # =========================================================================

    def get_active_ticker_items(
        self, now_iso: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetches active, non-expired ticker notifications ordered by urgency
        (CRITICAL -> NORMAL -> LOW) and creation timestamp. Automatically deserializes
        `action_payload` back into Python dictionaries.
        """
        target_time = now_iso or datetime.now(timezone.utc).isoformat()
        query = """
            SELECT id, category, urgency, message, action_type, action_payload, created_at, expires_at
            FROM idle_ticker_feed
            WHERE dismissed = 0 AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY 
              CASE urgency WHEN 'CRITICAL' THEN 1 WHEN 'NORMAL' THEN 2 ELSE 3 END,
              created_at DESC
            LIMIT ?;
        """
        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query, (target_time, limit))
            items = []
            for row in cursor.fetchall():
                item = dict(row)
                raw_payload = item.get("action_payload")
                if isinstance(raw_payload, str) and raw_payload.strip():
                    try:
                        item["action_payload"] = json.loads(raw_payload)
                    except Exception:
                        item["action_payload"] = {}
                else:
                    item["action_payload"] = {}
                items.append(item)
            return items

    # =========================================================================
    # 3. DISMISSAL & MAINTENANCE OPERATIONS
    # =========================================================================

    def dismiss_ticker_item(self, item_id: str) -> bool:
        """Flags a ticker notification item as dismissed (hides it from the UI)."""
        query = "UPDATE idle_ticker_feed SET dismissed = 1 WHERE id = ?;"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (item_id,))
            dismissed = cursor.rowcount > 0

        if dismissed:
            logger.info("Dismissed ticker item '%s'.", item_id)
        return dismissed

    def purge_expired_items(self) -> int:
        """Purges old expired or dismissed items from the table."""
        target_time = datetime.now(timezone.utc).isoformat()
        query = """
            DELETE FROM idle_ticker_feed 
            WHERE dismissed = 1 OR (expires_at IS NOT NULL AND expires_at <= ?);
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (target_time,))
            purged_count = cursor.rowcount

        if purged_count > 0:
            logger.info("Purged %d expired/dismissed ticker items.", purged_count)
        return purged_count