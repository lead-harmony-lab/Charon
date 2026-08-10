"""
charon/agents/machinist/printer.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Networked Hardware Transmission domain module.
"""

import logging
import os
from typing import Any, Dict, Optional, Union

from charon.agents.machinist.utils import resolve_file_path
from charon.intent import DynamicActionPayload
from charon.tools.cad import transmit_gcode_http

logger = logging.getLogger("CHAROND.Machinist.Printer")


def transmit_to_printer(
    default_printer_url: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
) -> str:
    """Transmits G-Code to a networked 3D printer or CNC machine."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    gcode_path = resolve_file_path(
        params,
        ["gcode_file", "file", "target_file"],
        [".gcode", ".g"],
        raw_prompt,
        payload,
    )

    if not gcode_path:
        return "Error: A 'gcode_file' parameter is required for transmission."

    if not gcode_path.exists():
        return f"Error: G-Code file {gcode_path} does not exist."

    target_url = (
        payload_params.get("printer_url")
        or getattr(payload, "printer_url", None)
        or params.get("printer_url")
        or default_printer_url
    )
    api_key = (
        payload_params.get("api_key")
        or getattr(payload, "api_key", None)
        or params.get("api_key")
        or os.getenv("PRINTER_API_KEY", "")
    )
    start_print = (
        payload_params.get("start_print")
        if payload_params.get("start_print") is not None
        else (getattr(payload, "start_print", None) if payload else None)
    )
    if start_print is None:
        start_print = params.get("start_print", False)

    dry_run = (
        payload_params.get("dry_run")
        if payload_params.get("dry_run") is not None
        else (getattr(payload, "dry_run", None) if payload else None)
    )
    if dry_run is None:
        dry_run = params.get("dry_run", False)

    return transmit_gcode_http(
        target_url=target_url,
        gcode_path=gcode_path,
        api_key=api_key,
        start_print=start_print,
        dry_run=dry_run,
    )