"""
charon/agents/overseer/databases.py
System Version: v0.1.0 | File Revision: 1.0.1

Module: Database resolution, integrity verification, and WAL/VACUUM optimization.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import (
    CHROMA_DB_DIR,
    QUARTERMASTER_DB_PATH,
    resolve_project_path,
)
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Overseer.Databases")


def resolve_target_databases(
    default_db_path: Optional[Path] = None,
    target: Optional[Union[str, Path]] = None,
) -> List[Path]:
    """Resolves target database paths, handling explicit file paths, directories, or default DBs."""
    targets: List[Path] = []
    raw_target = resolve_project_path(target) if target else default_db_path

    if raw_target:
        if raw_target.is_dir():
            for ext in ("*.sqlite3", "*.sqlite", "*.db"):
                targets.extend(raw_target.glob(ext))
        else:
            targets.append(raw_target)
    else:
        if QUARTERMASTER_DB_PATH.exists():
            targets.append(QUARTERMASTER_DB_PATH)

        chroma_sqlite = CHROMA_DB_DIR / "chroma.sqlite3"
        if chroma_sqlite.exists():
            targets.append(chroma_sqlite)

    return list(set(targets))


def vacuum_db_file(db_file: Path) -> Dict[str, Any]:
    """Performs integrity checks, PRAGMA optimization, WAL checkpoint, and VACUUM on a SQLite file."""
    if not db_file.exists() or not db_file.is_file():
        return {
            "file": str(db_file),
            "status": "skipped",
            "reason": "File not found or not a file",
        }

    size_before = db_file.stat().st_size
    try:
        with get_connection(db_file, timeout=10.0) as conn:
            # Enable autocommit mode required for VACUUM execution
            conn.isolation_level = None
            conn.execute("PRAGMA busy_timeout = 5000;")
            cursor = conn.cursor()

            cursor.execute("PRAGMA integrity_check;")
            integrity = cursor.fetchone()
            if not integrity or integrity[0] != "ok":
                return {
                    "file": str(db_file),
                    "status": "corrupted",
                    "reason": f"Integrity check failed: {integrity}",
                }

            cursor.execute("PRAGMA foreign_key_check;")
            fk_errors = cursor.fetchall()

            cursor.execute("PRAGMA optimize;")
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            cursor.execute("VACUUM;")

        size_after = db_file.stat().st_size
        bytes_freed = max(0, size_before - size_after)
        return {
            "file": str(db_file),
            "status": "success",
            "integrity": "ok",
            "fk_violations_count": len(fk_errors),
            "size_before_bytes": size_before,
            "size_after_bytes": size_after,
            "bytes_freed": bytes_freed,
        }
    except Exception as e:
        logger.error(f"Failed to optimize SQLite database {db_file}: {e}")
        return {"file": str(db_file), "status": "error", "error": str(e)}


async def optimize_sqlite_db(
    default_db_path: Optional[Path] = None,
    target_db: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Runs SQLite PRAGMA and VACUUM optimizations on target databases concurrently/off-thread."""
    target_files = resolve_target_databases(
        default_db_path=default_db_path, target=target_db
    )
    if not target_files:
        return {
            "status": "warning",
            "message": "No valid SQLite database files found to optimize.",
        }

    results = []
    for db_file in target_files:
        res = await asyncio.to_thread(vacuum_db_file, db_file)
        results.append(res)

    total_freed = sum(
        r.get("bytes_freed", 0)
        for r in results
        if r.get("status") == "success"
    )
    return {
        "status": "completed",
        "optimized_databases": results,
        "total_bytes_freed": total_freed,
    }