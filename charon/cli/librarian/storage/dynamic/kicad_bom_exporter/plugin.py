"""
Dynamic Skill Plugin: KiCad BOM Exporter
Action: export_kicad_bom
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger("Charon.Skills.KiCadBOMExporter")


def export_bom(
    agent_name: str, parameters: Dict[str, Any], raw_prompt: str = ""
) -> Union[str, Dict[str, Any]]:
    """Exports a Bill of Materials (BOM) CSV from a KiCad Schematic (.kicad_sch) using kicad-cli."""
    schematic_path_str = parameters.get("schematic_path") or parameters.get("file_path")
    if not schematic_path_str:
        return {"status": "error", "message": "Missing parameter 'schematic_path'"}

    sch_path = Path(schematic_path_str).resolve()
    if not sch_path.exists():
        return {"status": "error", "message": f"Schematic file not found at {sch_path}"}

    output_csv = sch_path.with_suffix(".bom.csv")
    cmd = [
        "kicad-cli",
        "sch",
        "export",
        "bom",
        str(sch_path),
        "--output",
        str(output_csv),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"[kicad_bom_exporter] BOM generated successfully: {output_csv}")
        return {
            "status": "success",
            "action": "export_kicad_bom",
            "output_file": str(output_csv),
            "stdout": res.stdout.strip(),
        }
    except subprocess.CalledProcessError as err:
        logger.error(f"[kicad_bom_exporter] Execution failed: {err.stderr}")
        return {
            "status": "failed",
            "error": err.stderr.strip(),
            "command": " ".join(cmd),
        }