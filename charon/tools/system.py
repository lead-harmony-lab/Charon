"""
charon/tools/system.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless System Diagnostics, Telemetry & Shell Execution Tools.
"""

import asyncio
import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from charon.config.paths import DATA_DIR

logger = logging.getLogger("Charon.Tools.System")


def get_system_info() -> str:
    """Gathers hardware, operating system, and runtime diagnostic info."""
    info = [
        f"OS: {platform.system()} {platform.release()} ({platform.architecture()[0]})",
        f"Python Version: {sys.version.split()[0]} ({sys.executable})",
        f"Hostname: {platform.node()}",
        f"Processor: {platform.processor() or 'Generic/System Native'}",
        f"Working Directory: {Path.cwd()}",
    ]

    if PSUTIL_AVAILABLE:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        info.append(f"CPU Load: {cpu_usage}%")
        info.append(
            f"RAM Usage: {mem.percent}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)"
        )
        info.append(
            f"Disk Usage: {disk.percent}% ({disk.free // (1024**3)}GB free)"
        )
    else:
        info.append(
            "psutil: Not installed (detailed hardware usage unavailable)"
        )

    return "System Status & Metrics:\n" + "\n".join(
        f"- {line}" for line in info
    )


def get_system_telemetry() -> Dict[str, Any]:
    """Retrieves structured OS host telemetry including CPU, RAM, RSS, and disk usage."""
    telemetry: Dict[str, Any] = {}

    if PSUTIL_AVAILABLE:
        vm = psutil.virtual_memory()
        proc = psutil.Process()
        telemetry["telemetry"] = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": vm.percent,
            "ram_available_mb": round(vm.available / (1024 * 1024), 2),
            "daemon_ram_rss_mb": round(
                proc.memory_info().rss / (1024 * 1024), 2
            ),
            "daemon_cpu_percent": proc.cpu_percent(interval=None),
        }
    else:
        telemetry["telemetry"] = {"psutil": "not_installed"}

    try:
        total, used, free = shutil.disk_usage(str(DATA_DIR.parent))
        telemetry["disk_usage"] = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "percent_used": round((used / total) * 100, 2),
        }
    except Exception as e:
        telemetry["disk_usage_error"] = str(e)

    return telemetry


async def execute_shell_command(
    command_str: str,
    timeout: float = 30.0,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Executes a shell command asynchronously with streaming output and timeout enforcement."""
    logger.info(f"Executing OS command: {command_str}")

    try:
        process = await asyncio.create_subprocess_shell(
            command_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_chunks = []

        async def _read_stream():
            if process.stdout is None:
                return
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                chunk = line.decode("utf-8", errors="replace")
                output_chunks.append(chunk)
                if stream_callback:
                    stream_callback(chunk)

        try:
            await asyncio.wait_for(_read_stream(), timeout=timeout)
            await process.wait()
            return_code = process.returncode
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"Command Execution Status: Failed (Execution timed out after {timeout}s)\n\nOutput:\nProcess killed due to timeout."

        full_output = "".join(output_chunks).strip()

        status = (
            "Success"
            if return_code == 0
            else f"Failed (exit code {return_code})"
        )
        output_display = (
            full_output
            if full_output
            else "(Command executed with no terminal output)"
        )
        return f"Command Execution Status: {status}\n\nOutput:\n{output_display}"

    except Exception as e:
        logger.error(f"Failed to execute system command '{command_str}': {e}")
        return f"System task execution error: {str(e)}"
