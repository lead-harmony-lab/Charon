"""Plugin entrypoint module for fab_printer_transmitter."""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from charon.tools.cad import transmit_gcode_http

logger = logging.getLogger("CHAROND.Skills.FabPrinterTransmitter")


def handle_transmit_to_printer(params: Dict[str, Any]) -> Dict[str, Any]:
    """Transmits G-Code to networked hardware."""
    raw_gcode = params.get("gcode_file") or params.get("file") or params.get("target_file")
    if not raw_gcode:
        return {"status": "error", "message": "Missing required 'gcode_file' parameter."}

    gcode_path = Path(raw_gcode).expanduser().resolve()
    if not gcode_path.exists():
        return {"status": "error", "message": f"G-Code file '{gcode_path}' does not exist."}

    target_url = params.get("printer_url") or os.getenv("PRINTER_URL", "http://192.168.1.100")
    api_key = params.get("api_key") or os.getenv("PRINTER_API_KEY", "")
    start_print = bool(params.get("start_print", False))
    dry_run = bool(params.get("dry_run", False))

    result = transmit_gcode_http(
        target_url=target_url,
        gcode_path=gcode_path,
        api_key=api_key,
        start_print=start_print,
        dry_run=dry_run,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for fab_printer_transmitter."""
    if action_name == "transmit_to_printer":
        return handle_transmit_to_printer(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'fab_printer_transmitter'.")