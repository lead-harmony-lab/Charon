"""
charon/agents/overseer/telemetry.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: System health metrics aggregation.
"""

import asyncio
import time
from typing import Any, Dict

from charon.config.paths import CHROMA_DB_DIR, QUARTERMASTER_DB_PATH
from charon.tools.system import get_system_telemetry


def get_health_sync() -> Dict[str, Any]:
    """Gathers host telemetry and system database file sizes."""
    health: Dict[str, Any] = {"timestamp": time.time()}

    health.update(get_system_telemetry())

    db_sizes = {}
    if QUARTERMASTER_DB_PATH.exists():
        db_sizes["quartermaster.db_bytes"] = (
            QUARTERMASTER_DB_PATH.stat().st_size
        )
    chroma_sqlite = CHROMA_DB_DIR / "chroma.sqlite3"
    if chroma_sqlite.exists():
        db_sizes["chroma.sqlite3_bytes"] = chroma_sqlite.stat().st_size
    health["database_sizes"] = db_sizes

    return health


async def get_system_health() -> Dict[str, Any]:
    """Asynchronously fetches host telemetry and health metrics."""
    return await asyncio.to_thread(get_health_sync)