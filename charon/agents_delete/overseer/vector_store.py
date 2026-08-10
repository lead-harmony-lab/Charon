"""
charon/agents/overseer/vector_store.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Vector store auditing and SQLite quick check inspections.
"""

import asyncio
import logging
from typing import Any, Dict

from charon.config.paths import CHROMA_DB_DIR
from charon.db.connection import get_connection

logger = logging.getLogger("charon.agents.overseer.vector_store")


def audit_vector_store_sync() -> Dict[str, Any]:
    """Audits Chroma vector store directory, collection structures, and sqlite integrity."""
    chroma_sqlite = CHROMA_DB_DIR / "chroma.sqlite3"
    details: Dict[str, Any] = {
        "directory": str(CHROMA_DB_DIR),
        "exists": CHROMA_DB_DIR.exists(),
    }

    if chroma_sqlite.exists():
        details["sqlite_size_bytes"] = chroma_sqlite.stat().st_size
        try:
            with get_connection(chroma_sqlite, timeout=10.0, read_only=True) as conn:
                conn.execute("PRAGMA busy_timeout = 5000;")
                cursor = conn.cursor()

                cursor.execute("PRAGMA quick_check;")
                check_res = cursor.fetchone()

                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                )
                tables = [r[0] for r in cursor.fetchall()]

                if "collections" in tables:
                    cursor.execute("SELECT COUNT(*) FROM collections;")
                    col_count = cursor.fetchone()
                else:
                    col_count = (0,)

                details["integrity_check"] = (
                    check_res[0] if check_res else "unknown"
                )
                details["active_collections_count"] = (
                    col_count[0] if col_count else 0
                )
        except Exception as e:
            logger.warning(f"Failed vector store SQLite integrity check: {e}")
            details["integrity_check"] = f"failed: {e}"
    else:
        details["sqlite_size_bytes"] = 0
        details["integrity_check"] = "no_sqlite_file"

    if CHROMA_DB_DIR.exists():
        collection_dirs = [
            d for d in CHROMA_DB_DIR.iterdir() if d.is_dir()
        ]
        details["collection_folders_count"] = len(collection_dirs)

    return details


async def audit_vector_store() -> Dict[str, Any]:
    """Asynchronously audits the vector store."""
    return await asyncio.to_thread(audit_vector_store_sync)