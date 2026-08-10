"""
charon/agents/spark/utils.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Path resolution and file locators for electrical projects.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from charon.config.paths import resolve_project_path


def resolve_project_dir(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Any = None,
) -> Optional[Path]:
    """Resolves project directory from explicit parameters, payload, or raw prompt text."""
    target = (
        (getattr(payload, "project_directory", None) if payload else None)
        or (getattr(payload, "project_name", None) if payload else None)
        or (getattr(payload, "project_path", None) if payload else None)
        or params.get("project_directory")
        or params.get("project_path")
        or params.get("project_name")
        or params.get("base_path")
        or raw_prompt.strip()
    )
    if not target:
        return None

    target_str = str(target).strip()
    if raw_prompt and not params and " " in target_str:
        tokens = target_str.split()
        target_str = tokens[-1]

    return resolve_project_path(target_str)


def find_pcb_file(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Any = None,
) -> Optional[Path]:
    """Locates a .kicad_pcb file from explicit parameters or project directory search."""
    pcb_file = (
        (getattr(payload, "pcb_file", None) if payload else None)
        or params.get("pcb_file")
        or params.get("file")
    )
    if pcb_file:
        path = Path(os.path.expanduser(str(pcb_file))).resolve()
        if path.exists():
            return path

    target_path = resolve_project_dir(params, raw_prompt, payload=payload)
    if target_path and target_path.exists():
        search_dirs = [
            target_path / "cad",
            target_path / "hardware",
            target_path,
        ]
        for sdir in search_dirs:
            if sdir.is_dir():
                pcb_files = list(sdir.glob("*.kicad_pcb"))
                if pcb_files:
                    return pcb_files[0].resolve()
    return None