"""
charon/sdk/telemetry.py
System Version: v0.1.0 | File Revision: 2.0.0

Hardware discovery and platform context aggregation.
"""

from datetime import datetime, timezone
import os
import platform
import shutil
import socket
from typing import Any, Dict, List


class HardwareTelemetry:
    """Utility class to discover local node hardware architecture and runtime context."""

    @staticmethod
    def get_local_ip() -> str:
        """Determines primary outbound local IP address."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def detect_gpus() -> List[str]:
        """Detects available GPU hardware using platform tools."""
        gpus = []
        if shutil.which("nvidia-smi"):
            try:
                import subprocess

                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0:
                    gpus.extend([
                        line.strip()
                        for line in res.stdout.strip().splitlines()
                        if line
                    ])
            except Exception:
                pass
        return gpus or ["None (CPU Only)"]

    @staticmethod
    def detect_usb_devices() -> List[str]:
        """Scans attached USB devices on Linux/macOS systems if tools exist."""
        devices = []
        if shutil.which("lsusb"):
            try:
                import subprocess

                res = subprocess.run(
                    ["lsusb"], capture_output=True, text=True, timeout=2
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().splitlines():
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            devices.append(parts[2].strip())
            except Exception:
                pass
        return devices[:10]  # Cap at 10 items to prevent payload bloat

    @classmethod
    def collect(cls) -> Dict[str, Any]:
        """Gathers full system telemetry snapshot."""
        try:
            total_disk, used_disk, free_disk = shutil.disk_usage("/")
            disk_info = {
                "total_gb": round(total_disk / (1024 ** 3), 2),
                "free_gb": round(free_disk / (1024 ** 3), 2),
            }
        except Exception:
            disk_info = {"total_gb": 0, "free_gb": 0}

        return {
            "hostname": socket.gethostname(),
            "ip_address": cls.get_local_ip(),
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "cpu_cores": os.cpu_count() or 1,
            "disk": disk_info,
            "gpus": cls.detect_gpus(),
            "usb_devices": cls.detect_usb_devices(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }