"""
charon/agents/overseer/resource_guard.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Resource inspection and pre-flight threshold guarding.
"""

import logging
from typing import Any, Dict, Tuple

import psutil

logger = logging.getLogger("Charon.Overseer.Guard")

try:
    import pynvml

    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


class SystemResourceGuard:
    """Pre-flight resource inspector to ensure background tasks don't collide with active user workloads."""

    def __init__(
        self,
        max_gpu_util: float = 15.0,
        max_vram_used_mb: float = 1500.0,
        max_cpu_util: float = 75.0,
    ):
        self.max_gpu_util = max_gpu_util
        self.max_vram_used_mb = max_vram_used_mb
        self.max_cpu_util = max_cpu_util

    def is_system_idle_for_llm(self) -> Tuple[bool, str]:
        """Returns True if GPU and CPU are sufficiently idle for background LLM workloads."""
        # 1. CPU Load Check
        cpu_load = psutil.cpu_percent(interval=0.5)
        if cpu_load > self.max_cpu_util:
            return False, f"CPU utilization high ({cpu_load}% > {self.max_cpu_util}%)"

        # 2. GPU Inspection (NVIDIA)
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()

                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                    vram_used_mb = mem_info.used / (1024 * 1024)

                    if util.gpu > self.max_gpu_util:
                        return False, f"GPU {i} compute active ({util.gpu}% utilization)"

                    if vram_used_mb > self.max_vram_used_mb:
                        return False, f"GPU {i} VRAM occupied ({vram_used_mb:.0f} MB used)"

            except Exception as e:
                logger.warning(f"NVML check failed: {e}")
            finally:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass

        return True, "System idle. Safe to invoke LLM background tasks."


async def audit_resource_guard() -> Dict[str, Any]:
    """Asynchronously audits process memory, disk utilization, GPU usage, and host limits."""
    guard = SystemResourceGuard()
    is_idle, reason = guard.is_system_idle_for_llm()

    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "action": "audit_resource_guard",
        "status": "completed",
        "is_idle_for_llm": is_idle,
        "idle_reason": reason,
        "metrics": {
            "cpu_utilization_pct": cpu_pct,
            "ram_utilization_pct": mem.percent,
            "ram_available_mb": round(mem.available / (1024 * 1024), 2),
            "disk_utilization_pct": disk.percent,
            "disk_free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
        },
    }