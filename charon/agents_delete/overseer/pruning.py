"""
charon/agents/overseer/pruning.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Workspace, log, and cache file retention and pruning logic for Overseer.
"""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from charon.config.paths import DATA_DIR, LOGS_DIR, WORKSPACES_DIR, XDG_CACHE_HOME

logger = logging.getLogger("Charon.Overseer.Pruning")


def _get_path_mtime_and_size(path: Path) -> Tuple[float, int]:
    """Calculates the max modification timestamp and total size in bytes for a path."""
    if path.is_file():
        try:
            st = path.stat()
            return st.st_mtime, st.st_size
        except OSError:
            return 0.0, 0

    max_mtime = path.stat().st_mtime if path.exists() else 0.0
    total_size = 0

    try:
        for item in path.rglob("*"):
            try:
                st = item.stat(follow_symlinks=False)
                if st.st_mtime > max_mtime:
                    max_mtime = st.st_mtime
                if item.is_file():
                    total_size += st.st_size
            except OSError:
                continue
    except OSError:
        pass

    return max_mtime, total_size


def prune_logs_sync(prune_days: int = 7) -> Dict[str, Any]:
    """Prunes log and cache files older than specified days."""
    cutoff_sec = time.time() - (prune_days * 86400)
    pruned_files = []
    bytes_reclaimed = 0

    target_dirs = [LOGS_DIR, DATA_DIR / "cache", XDG_CACHE_HOME / "charon"]
    for tdir in target_dirs:
        if not tdir.exists():
            continue
        for root, _, files in os.walk(tdir):
            for f in files:
                file_path = Path(root) / f
                try:
                    st = file_path.stat()
                    if st.st_mtime < cutoff_sec:
                        size = st.st_size
                        file_path.unlink()
                        pruned_files.append(str(file_path))
                        bytes_reclaimed += size
                except Exception as e:
                    logger.warning(
                        f"Failed to prune cache/log file {file_path}: {e}"
                    )

    freed_mb = round(bytes_reclaimed / (1024 * 1024), 2)
    logger.info(
        f"Log and cache pruning completed. Removed {len(pruned_files)} files ({freed_mb} MB freed)."
    )

    return {
        "action": "prune_logs_and_cache",
        "status": "completed",
        "prune_days_threshold": prune_days,
        "pruned_files_count": len(pruned_files),
        "bytes_reclaimed": bytes_reclaimed,
        "freed_mb": freed_mb,
    }


async def prune_logs_and_cache(prune_days: int = 7) -> Dict[str, Any]:
    """Asynchronously prunes old logs and cache files."""
    return await asyncio.to_thread(prune_logs_sync, prune_days)


def prune_stale_workspaces_sync(
    prune_days: int = 7,
    workspaces_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Scans WORKSPACES_DIR for task subdirectories and transient sandbox artifacts older
    than `prune_days` and removes them to reclaim disk space."""
    target_dir = Path(workspaces_dir).resolve() if workspaces_dir else WORKSPACES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    cutoff_timestamp = time.time() - (prune_days * 86400)
    pruned_items: List[str] = []
    bytes_reclaimed: int = 0
    errors: List[str] = []

    for item in target_dir.iterdir():
        # Preserve hidden files/directories (e.g., git metadata or lock files)
        if item.name.startswith("."):
            continue

        try:
            max_mtime, item_size = _get_path_mtime_and_size(item)

            if max_mtime < cutoff_timestamp:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

                bytes_reclaimed += item_size
                pruned_items.append(item.name)
                logger.info(
                    f"Pruned stale workspace artifact: {item.name} ({item_size} bytes)"
                )
        except Exception as e:
            err_msg = f"Failed to prune workspace item {item.name}: {e}"
            logger.warning(err_msg)
            errors.append(err_msg)

    freed_mb = round(bytes_reclaimed / (1024 * 1024), 2)
    logger.info(
        f"Workspace pruning completed. Pruned {len(pruned_items)} workspace folders/files ({freed_mb} MB freed)."
    )

    return {
        "action": "prune_stale_workspaces",
        "status": "completed",
        "workspaces_dir": str(target_dir),
        "prune_days_threshold": prune_days,
        "pruned_count": len(pruned_items),
        "pruned_items": pruned_items,
        "bytes_reclaimed": bytes_reclaimed,
        "freed_mb": freed_mb,
        "errors": errors,
    }


async def prune_stale_workspaces(
    prune_days: int = 7,
    workspaces_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Asynchronously prunes stale task sandboxes and workspace artifacts."""
    return await asyncio.to_thread(
        prune_stale_workspaces_sync, prune_days, workspaces_dir
    )