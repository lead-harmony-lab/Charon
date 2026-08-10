"""
charon/agents/spark/eda.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: High-level domain logic for KiCad Gerber and BOM exports.
"""

import logging
from typing import Any, Dict

from charon.agents.spark.utils import find_pcb_file
from charon.tools.eda import export_kicad_bom, export_kicad_gerbers

logger = logging.getLogger("Charon.Spark.EDA")


def handle_export_gerbers(
    kicad_cli: str,
    payload: Any,
    params: Dict[str, Any],
    raw_prompt: str = "",
) -> str:
    """Orchestrates Gerber and drill file exports from KiCad PCB files."""
    pcb_path = find_pcb_file(params, raw_prompt, payload=payload)
    if not pcb_path:
        return "Error: A valid 'pcb_file' or project containing a .kicad_pcb file is required to export gerbers."

    dry_run = bool(
        (getattr(payload, "dry_run", False) if payload else False)
        or params.get("dry_run", False)
    )

    return export_kicad_gerbers(
        pcb_path=pcb_path,
        kicad_cli=kicad_cli,
        dry_run=dry_run,
    )


def handle_export_bom(
    kicad_cli: str,
    payload: Any,
    params: Dict[str, Any],
    raw_prompt: str = "",
) -> str:
    """Orchestrates Bill of Materials (BOM) CSV export from KiCad schematic files."""
    pcb_path = find_pcb_file(params, raw_prompt, payload=payload)
    if not pcb_path:
        return "Error: A valid 'pcb_file' or project containing a .kicad_pcb file is required to export BOM."

    dry_run = bool(
        (getattr(payload, "dry_run", False) if payload else False)
        or params.get("dry_run", False)
    )

    return export_kicad_bom(
        pcb_path=pcb_path,
        kicad_cli=kicad_cli,
        dry_run=dry_run,
    )