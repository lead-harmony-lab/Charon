"""Plugin entrypoint module for fab_cad_tools."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.tools.cad import run_cad_export

logger = logging.getLogger("CHAROND.Skills.FabCadTools")


def _resolve_file_path(
    params: Dict[str, Any],
    keys: List[str],
    expected_extensions: Optional[List[str]] = None,
) -> Optional[Path]:
    """Internal helper to resolve input files from params or project directories."""
    raw_path = None
    for key in keys:
        if params.get(key):
            raw_path = str(params[key])
            break

    if not raw_path:
        proj = params.get("project_name") or params.get("project_directory")
        if proj:
            proj_path = resolve_project_path(proj)
            if proj_path.exists():
                search_dirs = [proj_path / "cad", proj_path / "models", proj_path / "3d", proj_path]
                exts = expected_extensions or [".stl", ".step", ".stp", ".fcstd", ".scad", ".gcode"]
                for sdir in search_dirs:
                    if sdir.is_dir():
                        for ext in exts:
                            matches = list(sdir.glob(f"*{ext}"))
                            if matches:
                                return matches[0].resolve()

    if not raw_path:
        return None

    try:
        path = Path(raw_path).expanduser().resolve()
        if path.exists():
            return path
    except Exception:
        pass

    candidate = resolve_project_path(raw_path)
    if candidate.exists():
        return candidate

    return Path(raw_path).expanduser().resolve()


def handle_export_cad_to_stl(params: Dict[str, Any]) -> Dict[str, Any]:
    """Executes CAD translation to generate STL geometry."""
    source_path = _resolve_file_path(
        params,
        ["source_file", "cad_file", "file", "input_file"],
        [".step", ".stp", ".fcstd", ".scad"],
    )

    if not source_path:
        return {"status": "error", "message": "Missing required 'source_file' or 'cad_file' parameter."}

    if not source_path.exists():
        return {"status": "error", "message": f"Source file '{source_path}' does not exist."}

    output_path = params.get("output_path")
    out_file = Path(output_path).expanduser().resolve() if output_path else source_path.with_suffix(".stl")
    dry_run = bool(params.get("dry_run", False))

    logger.info(f"Initiating CAD translation: {source_path.name} -> {out_file.name}")
    result = run_cad_export(source_path, out_file, dry_run=dry_run)
    return {"status": "success", "result": result}


def handle_inspect_cad_files(params: Dict[str, Any]) -> Dict[str, Any]:
    """Indexes CAD, STL, and G-Code artifacts in workspace directories."""
    proj = params.get("project_name") or params.get("project_directory") or params.get("base_path")
    target_dir = resolve_project_path(proj) if proj else PROJECTS_DIR

    if not target_dir.exists():
        return {"status": "error", "message": f"Target directory '{target_dir}' does not exist."}

    extensions = {".step", ".stp", ".scad", ".fcstd", ".stl", ".3mf", ".gcode"}
    found_files = []

    for full_p in sorted(target_dir.rglob("*")):
        if full_p.is_file() and full_p.suffix.lower() in extensions:
            rel_p = full_p.relative_to(target_dir)
            size_kb = round(full_p.stat().st_size / 1024, 1)
            found_files.append(f" • {rel_p} ({size_kb} KB)")

    if not found_files:
        return {"status": "success", "result": f"No fabrication artifacts found in {target_dir}."}

    output = f"Fabrication artifacts in {target_dir}:\n" + "\n".join(found_files)
    return {"status": "success", "result": output}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for fab_cad_tools."""
    if action_name == "export_cad_to_stl":
        return handle_export_cad_to_stl(params)
    elif action_name == "inspect_cad_files":
        return handle_inspect_cad_files(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'fab_cad_tools'.")