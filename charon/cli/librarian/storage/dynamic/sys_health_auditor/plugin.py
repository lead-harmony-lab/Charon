"""Plugin entrypoint module for sys_health_auditor."""

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import psutil

# Optional GPU monitoring
try:
    import pynvml

    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

# Ecosystem mock/fallbacks for standalone extraction
try:
    from charon.config.paths import (
        CHROMA_DB_DIR,
        QUARTERMASTER_DB_PATH,
        STATE_DB_PATH,
        resolve_project_path,
    )
    from charon.db.connection import get_connection
    from charon.tools.system import get_system_telemetry
except ImportError:
    CHROMA_DB_DIR = Path("/tmp/charon/chroma")
    QUARTERMASTER_DB_PATH = Path("/tmp/charon/quartermaster.db")
    STATE_DB_PATH = Path("/tmp/charon/charon_state.db")


    def resolve_project_path(p):
        return Path(p).resolve() if p else None


    def get_system_telemetry():
        return {"mock_telemetry": "active"}


    class DummyConnection:
        def __init__(self, *args, **kwargs): self.isolation_level = None

        def __enter__(self): return self

        def __exit__(self, *args): pass

        def cursor(self): return self

        def execute(self, *args): pass

        def fetchone(self): return ("ok",)

        def fetchall(self): return []


    def get_connection(*args, **kwargs):
        return DummyConnection()

logger = logging.getLogger("CHAROND.Skills.sys_health_auditor")
DAEMON_IPC_URL = "http://127.0.0.1:8000/api/v1/internal/events/gap-detected"


# --- Core Logic Functions ---

def _resolve_target_databases(target: Optional[Union[str, Path]] = None) -> List[Path]:
    targets: List[Path] = []
    raw_target = resolve_project_path(target)

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


def _vacuum_db_file(db_file: Path) -> Dict[str, Any]:
    if not db_file.exists() or not db_file.is_file():
        return {"file": str(db_file), "status": "skipped", "reason": "Not found"}

    size_before = db_file.stat().st_size
    try:
        with get_connection(db_file, timeout=10.0) as conn:
            conn.isolation_level = None
            conn.execute("PRAGMA busy_timeout = 5000;")
            cursor = conn.cursor()

            cursor.execute("PRAGMA integrity_check;")
            integrity = cursor.fetchone()
            if not integrity or integrity[0] != "ok":
                return {"file": str(db_file), "status": "corrupted", "reason": f"Check failed: {integrity}"}

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


def _audit_vector_store_sync() -> Dict[str, Any]:
    chroma_sqlite = CHROMA_DB_DIR / "chroma.sqlite3"
    details = {"directory": str(CHROMA_DB_DIR), "exists": CHROMA_DB_DIR.exists()}

    if chroma_sqlite.exists():
        details["sqlite_size_bytes"] = chroma_sqlite.stat().st_size
        try:
            with get_connection(chroma_sqlite, timeout=10.0, read_only=True) as conn:
                conn.execute("PRAGMA busy_timeout = 5000;")
                cursor = conn.cursor()
                cursor.execute("PRAGMA quick_check;")
                check_res = cursor.fetchone()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]

                if "collections" in tables:
                    cursor.execute("SELECT COUNT(*) FROM collections;")
                    col_count = cursor.fetchone()
                else:
                    col_count = (0,)

                details["integrity_check"] = check_res[0] if check_res else "unknown"
                details["active_collections_count"] = col_count[0] if col_count else 0
        except Exception as e:
            details["integrity_check"] = f"failed: {e}"
    else:
        details["sqlite_size_bytes"] = 0
        details["integrity_check"] = "no_sqlite_file"

    if CHROMA_DB_DIR.exists():
        collection_dirs = [d for d in CHROMA_DB_DIR.iterdir() if d.is_dir()]
        details["collection_folders_count"] = len(collection_dirs)

    return details


def _get_health_sync() -> Dict[str, Any]:
    health = {"timestamp": time.time()}
    health.update(get_system_telemetry())

    db_sizes = {}
    if QUARTERMASTER_DB_PATH.exists():
        db_sizes["quartermaster.db_bytes"] = QUARTERMASTER_DB_PATH.stat().st_size
    chroma_sqlite = CHROMA_DB_DIR / "chroma.sqlite3"
    if chroma_sqlite.exists():
        db_sizes["chroma.sqlite3_bytes"] = chroma_sqlite.stat().st_size

    health["database_sizes"] = db_sizes
    return health


def _sweep_and_resolve_gaps_sync() -> Dict[str, Any]:
    if not STATE_DB_PATH.exists():
        return {"status": "skipped", "reason": "charon_state.db not found"}

    resolved_count, failed_count = 0, 0
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT gap_id, action_name, requesting_agent, context_json FROM skill_gaps WHERE status = 'open'")
        open_gaps = cursor.fetchall()

        if not open_gaps:
            return {"status": "completed", "gaps_resolved": 0, "message": "No open gaps found."}

        for gap in open_gaps:
            gap_id = gap[0] if isinstance(gap, tuple) else gap.get("gap_id")
            action_name = gap[1] if isinstance(gap, tuple) else gap.get("action_name")
            agent = gap[2] if isinstance(gap, tuple) else gap.get("requesting_agent")
            raw_context = gap[3] if isinstance(gap, tuple) else gap.get("context_json")

            try:
                context = json.loads(raw_context) if raw_context else {}
            except json.JSONDecodeError:
                context = {}

            payload = {
                "gap_id": gap_id, "action_name": action_name,
                "requesting_agent": agent, "context": context,
            }
            try:
                httpx.post(DAEMON_IPC_URL, json=payload, timeout=2.0)
            except httpx.RequestError as e:
                logger.warning(f"Daemon IPC unreachable: {e}")

            inferred_skill_id = f"{action_name}_skill".replace("__", "_")
            try:
                subprocess.run(
                    ["charon-forge", "scaffold", "--skill-id", inferred_skill_id, "--action", action_name],
                    check=True, capture_output=True, text=True,
                )
                cursor.execute("UPDATE skill_gaps SET status = 'in_progress' WHERE gap_id = ?", (gap_id,))
                resolved_count += 1
            except subprocess.CalledProcessError as e:
                logger.error(f"Forge execution failed for {inferred_skill_id}: {e.stderr}")
                failed_count += 1

    return {"status": "completed", "gaps_scaffolded": resolved_count, "gaps_failed": failed_count}


class SystemResourceGuard:
    def __init__(self, max_gpu_util=15.0, max_vram_used_mb=1500.0, max_cpu_util=75.0):
        self.max_gpu_util = max_gpu_util
        self.max_vram_used_mb = max_vram_used_mb
        self.max_cpu_util = max_cpu_util

    def is_system_idle_for_llm(self) -> Tuple[bool, str]:
        cpu_load = psutil.cpu_percent(interval=0.5)
        if cpu_load > self.max_cpu_util:
            return False, f"CPU utilization high ({cpu_load}% > {self.max_cpu_util}%)"

        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                for i in range(pynvml.nvmlDeviceGetCount()):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    vram_used_mb = mem_info.used / (1024 * 1024)

                    if util.gpu > self.max_gpu_util:
                        return False, f"GPU {i} compute active ({util.gpu}% utilization)"
                    if vram_used_mb > self.max_vram_used_mb:
                        return False, f"GPU {i} VRAM occupied ({vram_used_mb:.0f} MB used)"
            except Exception:
                pass
            finally:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass

        return True, "System idle. Safe to invoke LLM background tasks."


# --- Async Handlers ---

async def handle_optimize_databases(params: Dict[str, Any]) -> Dict[str, Any]:
    target_db = params.get("target_db")
    target_files = _resolve_target_databases(target=target_db)

    if not target_files:
        return {"status": "warning", "message": "No valid SQLite database files found."}

    results = []
    for db_file in target_files:
        res = await asyncio.to_thread(_vacuum_db_file, db_file)
        results.append(res)

    total_freed = sum(r.get("bytes_freed", 0) for r in results if r.get("status") == "success")
    return {"status": "completed", "optimized_databases": results, "total_bytes_freed": total_freed}


async def handle_audit_vector_store(params: Dict[str, Any]) -> Dict[str, Any]:
    return await asyncio.to_thread(_audit_vector_store_sync)


async def handle_get_system_health(params: Dict[str, Any]) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_health_sync)


async def handle_resolve_skill_gaps(params: Dict[str, Any]) -> Dict[str, Any]:
    return await asyncio.to_thread(_sweep_and_resolve_gaps_sync)


async def handle_audit_resource_guard(params: Dict[str, Any]) -> Dict[str, Any]:
    guard = SystemResourceGuard()
    is_idle, reason = await asyncio.to_thread(guard.is_system_idle_for_llm)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "action": "audit_resource_guard",
        "status": "completed",
        "is_idle_for_llm": is_idle,
        "idle_reason": reason,
        "metrics": {
            "cpu_utilization_pct": psutil.cpu_percent(interval=0.1),
            "ram_utilization_pct": mem.percent,
            "ram_available_mb": round(mem.available / (1024 * 1024), 2),
            "disk_utilization_pct": disk.percent,
            "disk_free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
        }
    }


# --- Router ---

def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    routes = {
        "optimize_databases": handle_optimize_databases,
        "audit_vector_store": handle_audit_vector_store,
        "get_system_health": handle_get_system_health,
        "audit_resource_guard": handle_audit_resource_guard,
        "resolve_skill_gaps": handle_resolve_skill_gaps,
    }

    handler = routes.get(action_name)
    if not handler:
        raise ValueError(f"Action '{action_name}' is not supported by skill 'sys_health_auditor'.")

    return asyncio.run(handler(params))