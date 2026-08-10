"""
charon/agents/spark/firmware.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: High-level domain logic for firmware builds and flashing.
"""

import logging
from typing import Any, Dict

from charon.agents.spark.utils import resolve_project_dir
from charon.tools.firmware import (
    compile_platformio_firmware,
    flash_platformio_firmware,
)

logger = logging.getLogger("Charon.Spark.Firmware")


def handle_compile_firmware(
    pio_cmd: str,
    payload: Any,
    params: Dict[str, Any],
    raw_prompt: str = "",
) -> str:
    """Orchestrates firmware compilation using PlatformIO."""
    target_path = resolve_project_dir(params, raw_prompt, payload=payload)
    if not target_path:
        return "Error: A 'project_directory' or 'project_name' parameter is required for compilation."

    if (target_path / "firmware").is_dir() and (
        target_path / "firmware" / "platformio.ini"
    ).exists():
        target_path = target_path / "firmware"

    if not target_path.exists():
        return f"Error: Project directory {target_path} does not exist."

    env = (
        (getattr(payload, "environment", None) if payload else None)
        or params.get("environment")
        or params.get("env")
        or ""
    )
    dry_run = bool(
        (getattr(payload, "dry_run", False) if payload else False)
        or params.get("dry_run", False)
    )

    return compile_platformio_firmware(
        target_path=target_path,
        pio_cmd=pio_cmd,
        environment=str(env),
        dry_run=dry_run,
    )


def handle_flash_hardware(
    pio_cmd: str,
    payload: Any,
    params: Dict[str, Any],
    raw_prompt: str = "",
) -> str:
    """Orchestrates flashing binaries to microcontroller hardware."""
    target_path = resolve_project_dir(params, raw_prompt, payload=payload)
    if not target_path:
        return "Error: A 'project_directory' or 'project_name' parameter is required for flashing."

    if (target_path / "firmware").is_dir() and (
        target_path / "firmware" / "platformio.ini"
    ).exists():
        target_path = target_path / "firmware"

    if not target_path.exists():
        return f"Error: Project directory {target_path} does not exist."

    port = (
        (getattr(payload, "port", None) if payload else None)
        or params.get("port")
        or params.get("upload_port")
        or "auto"
    )
    env = (
        (getattr(payload, "environment", None) if payload else None)
        or params.get("environment")
        or params.get("env")
        or ""
    )
    dry_run = bool(
        (getattr(payload, "dry_run", False) if payload else False)
        or params.get("dry_run", False)
    )

    return flash_platformio_firmware(
        target_path=target_path,
        pio_cmd=pio_cmd,
        port=str(port),
        environment=str(env),
        dry_run=dry_run,
    )