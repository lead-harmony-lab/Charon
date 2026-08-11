"""Plugin entrypoint module for sys_asset_pruner."""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ecosystem mock/fallbacks for standalone extraction
try:
    from charon.config.paths import (
        DATA_DIR,
        DATASHEETS_DIR,
        LOGS_DIR,
        QUARTERMASTER_DB_PATH,
        WORKSPACES_DIR,
        XDG_CACHE_HOME,
        resolve_project_path,
    )
    from charon.db.connection import get_connection
except ImportError:
    # Fallbacks for standalone testing outside the Charon ecosystem
    DATA_DIR = Path("/tmp/charon/data")
    DATASHEETS_DIR = Path("/tmp/charon/datasheets")
    LOGS_DIR = Path("/tmp/charon/logs")
    QUARTERMASTER_DB_PATH = Path("/tmp/charon/quartermaster.db")
    WORKSPACES_DIR = Path("/tmp/charon/workspaces")
    XDG_CACHE_HOME = Path("/tmp/cache")

    def resolve_project_path(p): return Path(p).resolve() if p else None

    class DummyConnection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, *args): pass
        def fetchone(self): return None
        def fetchall(self): return []

    def get_connection(*args, **kwargs): return DummyConnection()

logger = logging.getLogger("CHAROND.Skills.sys_asset_pruner")


# --- Core Logic Functions ---

def _prune_orphaned_assets_sync(datasheets_dir: str = None) -> Dict[str, Any]:
    """Sweeps workspace directories for broken symlinks or unlinked files."""
    target_dir = resolve_project_path(datasheets_dir) if datasheets_dir else DATASHEETS_DIR

    if not target_dir.exists():
        return {"status": "skipped", "reason": f"Directory {target_dir} does not exist."}

    registered_files = set()
    if QUARTERMASTER_DB_PATH.exists():
        try:
            with get_connection(QUARTERMASTER_DB_PATH, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='datasheets';")
                if cursor.fetchone():
                    cursor.execute("SELECT file_path FROM datasheets WHERE file_path IS NOT NULL;")
                    for row in cursor.fetchall():
                        if row[0]:
                            registered_files.add(Path(row[0]).resolve())
        except Exception as e:
            logger.warning(f"Failed to query quartermaster.db for registered datasheets: {e}")

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

def _prune_logs_sync(prune_days: int = 7) -> Dict[str, Any]:
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
                    logger.warning(f"Failed to prune cache/log file {file_path}: {e}")

    freed_mb = round(bytes_reclaimed / (1024 * 1024), 2)
    return {
        "action": "prune_logs_and_cache",
        "status": "completed",
        "prune_days_threshold": prune_days,
        "pruned_files_count": len(pruned_files),
        "bytes_reclaimed": bytes_reclaimed,
        "freed_mb": freed_mb,
    }

def _prune_stale_workspaces_sync(prune_days: int = 7, workspaces_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Scans WORKSPACES_DIR for task subdirectories and transient sandbox artifacts older than `prune_days`."""
    target_dir = Path(workspaces_dir).resolve() if workspaces_dir else WORKSPACES_DIR
    if not target_dir.exists() or not target_dir.is_dir():
        return {"status": "skipped", "reason": f"{target_dir} is not a valid directory."}

    cutoff_sec = time.time() - (prune_days * 86400)
    pruned_dirs = []
    bytes_reclaimed = 0

    for item in target_dir.iterdir():
        if not item.is_dir():
            continue
        mtime, size = _get_path_mtime_and_size(item)
        if mtime < cutoff_sec:
            try:
                shutil.rmtree(item)
                pruned_dirs.append(item.name)
                bytes_reclaimed += size
            except Exception as e:
                logger.error(f"Failed to prune workspace {item}: {e}")

    freed_mb = round(bytes_reclaimed / (1024 * 1024), 2)
    return {
        "action": "prune_stale_workspaces",
        "status": "completed",
        "prune_days_threshold": prune_days,
        "pruned_workspaces": pruned_dirs,
        "pruned_workspaces_count": len(pruned_dirs),
        "bytes_reclaimed": bytes_reclaimed,
        "freed_mb": freed_mb,
    }


# --- Async Handlers ---

async def handle_prune_orphaned_assets(params: Dict[str, Any]) -> Dict[str, Any]:
    target_dir = params.get("datasheets_dir")
    return await asyncio.to_thread(_prune_orphaned_assets_sync, target_dir)

async def handle_prune_stale_workspaces(params: Dict[str, Any]) -> Dict[str, Any]:
    prune_days = params.get("prune_days", 7)
    workspaces_dir = params.get("workspaces_dir")
    return await asyncio.to_thread(_prune_stale_workspaces_sync, prune_days, workspaces_dir)

async def handle_prune_logs_and_cache(params: Dict[str, Any]) -> Dict[str, Any]:
    prune_days = params.get("prune_days", 7)
    return await asyncio.to_thread(_prune_logs_sync, prune_days)

# --- Router ---

def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    routes = {
        "prune_orphaned_assets": handle_prune_orphaned_assets,
        "prune_stale_workspaces": handle_prune_stale_workspaces,
        "prune_logs_and_cache": handle_prune_logs_and_cache,
    }

    handler = routes.get(action_name)
    if not handler:
        raise ValueError(f"Action '{action_name}' is not supported by skill 'sys_asset_pruner'.")

    return asyncio.run(handler(params))