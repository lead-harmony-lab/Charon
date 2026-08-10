"""
charon/agents/machinist/slicing.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: CAM Slicing and G-Code generation domain module.
"""

import logging
import shutil
from typing import Any, Dict, Optional, Union

from charon.agents.machinist.utils import resolve_file_path
from charon.intent import DynamicActionPayload
from charon.tools.cad import run_slicer

logger = logging.getLogger("CHAROND.Machinist.Slicing")


def detect_slicer() -> Optional[str]:
    """Detects available slicers installed on the system PATH."""
    candidates = ["prusa-slicer", "orca-slicer", "slic3r", "cura-cli"]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return "prusa-slicer"  # Fallback default executable name


def generate_gcode(
    slicer_cmd: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
) -> str:
    """Invokes local slicer to generate CAM G-Code toolpaths."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    stl_path = resolve_file_path(
        params,
        ["stl_file", "geometry_file", "source_file", "file"],
        [".stl", ".3mf", ".obj"],
        raw_prompt,
        payload,
    )

    if not stl_path:
        return "Error: An 'stl_file' or 3D geometry file parameter is required to generate toolpaths."

    if not stl_path.exists():
        return f"Error: The geometry file {stl_path} cannot be located."

    profile = (
        payload_params.get("profile")
        or payload_params.get("slicer_profile")
        or getattr(payload, "profile", None)
        or getattr(payload, "slicer_profile", None)
        or params.get("profile")
        or params.get("slicer_profile")
    )
    layer_height = (
        payload_params.get("layer_height")
        or getattr(payload, "layer_height", None)
        or params.get("layer_height")
    )
    infill = (
        payload_params.get("infill")
        or getattr(payload, "infill", None)
        or params.get("infill")
    )
    dry_run = (
        payload_params.get("dry_run")
        if payload_params.get("dry_run") is not None
        else (getattr(payload, "dry_run", None) if payload else None)
    )
    if dry_run is None:
        dry_run = params.get("dry_run", False)

    gcode_path = stl_path.with_suffix(".gcode")

    return run_slicer(
        slicer_cmd=slicer_cmd,
        stl_path=stl_path,
        gcode_path=gcode_path,
        profile=profile,
        layer_height=layer_height,
        infill=infill,
        dry_run=dry_run,
    )