"""Plugin entrypoint module for fab_cam_slicer."""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from charon.tools.cad import run_slicer

logger = logging.getLogger("CHAROND.Skills.FabCamSlicer")


def _detect_slicer() -> str:
    """Detects available slicers installed on system PATH."""
    candidates = ["prusa-slicer", "orca-slicer", "slic3r", "cura-cli"]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return "prusa-slicer"


def handle_generate_gcode(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generates CAM G-Code toolpaths from geometry."""
    raw_stl = params.get("stl_file") or params.get("geometry_file") or params.get("source_file") or params.get("file")
    if not raw_stl:
        return {"status": "error", "message": "Missing required 'stl_file' parameter."}

    stl_path = Path(raw_stl).expanduser().resolve()
    if not stl_path.exists():
        return {"status": "error", "message": f"Geometry file '{stl_path}' does not exist."}

    slicer_cmd = params.get("slicer_cmd") or _detect_slicer()
    profile = params.get("profile") or params.get("slicer_profile")
    layer_height = params.get("layer_height")
    infill = params.get("infill")
    dry_run = bool(params.get("dry_run", False))
    gcode_path = stl_path.with_suffix(".gcode")

    result = run_slicer(
        slicer_cmd=slicer_cmd,
        stl_path=stl_path,
        gcode_path=gcode_path,
        profile=profile,
        layer_height=layer_height,
        infill=infill,
        dry_run=dry_run,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for fab_cam_slicer."""
    if action_name == "generate_gcode":
        return handle_generate_gcode(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'fab_cam_slicer'.")