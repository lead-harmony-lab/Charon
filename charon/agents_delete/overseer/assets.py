"""
charon/agents/overseer/assets.py
System Version: v0.1.0 | File Revision: 1.0.1

Module: Orphaned workspace file and broken symlink cleanup.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config.paths import (
    DATASHEETS_DIR,
    QUARTERMASTER_DB_PATH,
    resolve_project_path,
)
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Overseer.Assets")


def prune_orphaned_assets_sync(
    datasheets_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Sweeps workspace directories for broken symlinks or unlinked PDF files."""
    target_dir = (
        resolve_project_path(datasheets_dir)
        if datasheets_dir
        else DATASHEETS_DIR
    )

    if not target_dir.exists():
        return {
            "status": "skipped",
            "reason": f"Directory {target_dir} does not exist.",
        }

    registered_files = set()
    if QUARTERMASTER_DB_PATH.exists():
        try:
            # Safely open transactional read-only context manager
            with get_connection(QUARTERMASTER_DB_PATH, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='datasheets';"
                )
                if cursor.fetchone():
                    cursor.execute(
                        "SELECT file_path FROM datasheets WHERE file_path IS NOT NULL;"
                    )
                    for row in cursor.fetchall():
                        if row[0]:
                            registered_files.add(Path(row[0]).resolve())
        except Exception as e:
            logger.warning(
                f"Failed to query quartermaster.db for registered datasheets: {e}"
            )

    orphaned_files = []
    broken_symlinks = []
    bytes_reclaimed = 0

    for root, _, files in os.walk(target_dir):
        for f in files:
            file_path = Path(root) / f

            if file_path.is_symlink() and not file_path.exists():
                broken_symlinks.append(str(file_path))
                file_path.unlink()
                continue

            resolved = file_path.resolve()
            if registered_files and resolved not in registered_files:
                size = file_path.stat().st_size
                orphaned_files.append(str(file_path))
                file_path.unlink()
                bytes_reclaimed += size

    return {
        "status": "completed",
        "target_dir": str(target_dir),
        "broken_symlinks_removed": len(broken_symlinks),
        "orphaned_files_removed": len(orphaned_files),
        "bytes_reclaimed": bytes_reclaimed,
    }


async def prune_orphaned_assets(
    datasheets_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Asynchronously sweeps workspace directories for broken symlinks or unlinked assets."""
    return await asyncio.to_thread(
        prune_orphaned_assets_sync, datasheets_dir
    )