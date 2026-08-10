"""
charon/agents/machinist/utils.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Path resolution utilities for fabrication assets.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import resolve_project_path
from charon.intent import DynamicActionPayload


def resolve_file_path(
    params: Dict[str, Any],
    keys: List[str],
    expected_extensions: Optional[List[str]] = None,
    raw_prompt: str = "",
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> Optional[Path]:
    """Resolves target input files from explicit paths, project names, or workspace subdirectories."""
    raw_path = None
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )

    if payload:
        for key in keys:
            val = payload_params.get(key) or getattr(payload, key, None)
            if val:
                raw_path = str(val)
                break

    if not raw_path:
        for key in keys:
            if params.get(key):
                raw_path = str(params[key])
                break

    if not raw_path and raw_prompt:
        raw_path = raw_prompt.strip()

    if not raw_path:
        # Fall back to project directory search
        proj = (
            payload_params.get("project_name")
            or payload_params.get("project_directory")
            or getattr(payload, "project_name", None)
            or getattr(payload, "project_directory", None)
            or params.get("project_name")
            or params.get("project_directory")
        )
        if proj:
            proj_path = resolve_project_path(proj)
            if proj_path.exists():
                search_dirs = [
                    proj_path / "cad",
                    proj_path / "models",
                    proj_path / "3d",
                    proj_path,
                ]
                exts = expected_extensions or [
                    ".stl",
                    ".step",
                    ".stp",
                    ".fcstd",
                    ".scad",
                    ".gcode",
                ]
                for sdir in search_dirs:
                    if sdir.is_dir():
                        for ext in exts:
                            matches = list(sdir.glob(f"*{ext}"))
                            if matches:
                                return matches[0].resolve()

    if not raw_path:
        return None

    # Resolve raw path using pathlib and resolve_project_path
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