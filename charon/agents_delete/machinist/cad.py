"""
charon/agents/machinist/cad.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: CAD Inspection and Translation domain module.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.machinist.utils import resolve_file_path
from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.intent import DynamicActionPayload
from charon.tools.cad import run_cad_export

logger = logging.getLogger("CHAROND.Machinist.CAD")


def export_cad_to_stl(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
) -> str:
    """Executes CAD translation to generate STL geometry."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    source_path = resolve_file_path(
        params,
        ["source_file", "cad_file", "file", "input_file"],
        [".step", ".stp", ".fcstd", ".scad"],
        raw_prompt,
        payload,
    )

    if not source_path:
        return "Error: A valid 'source_file' or 'cad_file' parameter is required for CAD export."

    if not source_path.exists():
        return f"Error: The source file {source_path} cannot be located."

    output_path = (
        payload_params.get("output_path")
        or getattr(payload, "output_path", None)
        or params.get("output_path")
    )
    out_file = (
        Path(output_path).expanduser().resolve()
        if output_path
        else source_path.with_suffix(".stl")
    )

    dry_run = (
        payload_params.get("dry_run")
        if payload_params.get("dry_run") is not None
        else (getattr(payload, "dry_run", None) if payload else None)
    )
    if dry_run is None:
        dry_run = params.get("dry_run", False)

    logger.info(
        f"Initiating CAD translation: {source_path.name} -> {out_file.name}"
    )

    return run_cad_export(source_path, out_file, dry_run=dry_run)


def inspect_cad_files(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
) -> str:
    """Indexes CAD, STL, and G-Code artifacts within a target workspace directory."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    proj = (
        payload_params.get("project_name")
        or payload_params.get("project_directory")
        or payload_params.get("base_path")
        or getattr(payload, "project_name", None)
        or getattr(payload, "project_directory", None)
        or getattr(payload, "base_path", None)
        or params.get("project_name")
        or params.get("project_directory")
        or params.get("base_path")
        or raw_prompt
    )

    target_dir = (
        resolve_project_path(proj)
        if proj
        else PROJECTS_DIR
    )

    if not target_dir.exists():
        return f"Directory {target_dir} does not exist."

    extensions = {
        ".step",
        ".stp",
        ".scad",
        ".fcstd",
        ".stl",
        ".3mf",
        ".gcode",
    }
    found_files = []

    for full_p in sorted(target_dir.rglob("*")):
        if full_p.is_file() and full_p.suffix.lower() in extensions:
            rel_p = full_p.relative_to(target_dir)
            size_kb = round(full_p.stat().st_size / 1024, 1)
            found_files.append(f" • {rel_p} ({size_kb} KB)")

    if not found_files:
        return f"No CAD/CAM fabrication files found in {target_dir}."

    return f"Fabrication artifacts in {target_dir}:\n" + "\n".join(
        found_files
    )