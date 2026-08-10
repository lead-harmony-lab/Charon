"""
charon/agents/cleaner/cad.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: CAD version sweep domain module for The Cleaner.
Updated for DynamicActionPayload intent parsing.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.agents.cleaner.utils import get_param
from charon.config.paths import PROJECTS_DIR
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Cleaner.CAD")


class CADManager:
    """Manages CAD version sweeping and archiving deprecated iterations."""

    def __init__(self, projects_dir: Optional[Union[str, Path]] = None):
        self.projects_dir = (
            Path(projects_dir).resolve() if projects_dir else PROJECTS_DIR
        )

    def sweep_cad_iterations(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Locates iterative CAD files (e.g. bracket_v1.step) and archives deprecated versions."""
        params = params or {}
        project_name = get_param(payload, params, "project_name")
        base_path_str = get_param(
            payload, params, "base_path", "project_directory", "target_path"
        )

        if base_path_str:
            target_path = Path(str(base_path_str)).expanduser().resolve()
            if project_name and (target_path / str(project_name)).is_dir():
                target_path = target_path / str(project_name)
        elif project_name:
            target_path = self.projects_dir / str(project_name)
        else:
            return "Error: A 'project_name' or 'base_path' parameter is required to sweep CAD iterations."

        cad_dir = (
            target_path / "cad"
            if (target_path / "cad").is_dir()
            else target_path
        )

        if not cad_dir.exists():
            return f"CAD directory not found at {cad_dir}."

        pattern = re.compile(
            r"^(.*?)[_.-]v(\d+)\.([a-zA-Z0-9]+)$", re.IGNORECASE
        )
        grouped_files: Dict[tuple, List[tuple]] = {}

        for item in cad_dir.iterdir():
            if item.is_file():
                match = pattern.match(item.name)
                if match:
                    base_name, version_str, ext = match.groups()
                    key = (base_name.lower(), ext.lower())
                    version = int(version_str)
                    grouped_files.setdefault(key, []).append((version, item))

        if not grouped_files:
            return f"No versioned CAD iterations (e.g. *_v1.step) found in {cad_dir}."

        archive_dir = cad_dir / "archive"
        archived_files = []

        for key, files in grouped_files.items():
            if len(files) <= 1:
                continue

            files.sort(key=lambda x: x[0])

            for version, file_path in files[:-1]:
                archive_dir.mkdir(parents=True, exist_ok=True)
                dest = archive_dir / file_path.name
                shutil.move(str(file_path), str(dest))
                archived_files.append(
                    f"{file_path.name} -> archive/{file_path.name}"
                )

        if not archived_files:
            return f"All CAD files in {cad_dir} are up to date. No deprecated iterations swept."

        summary = (
            f"[SYSTEM EXECUTION REPORT]\n"
            f"Action : CAD Iteration Sweep\n"
            f"Target : {cad_dir}\n"
            f"Archived Iterations:\n"
        )
        summary += "\n".join([f" • {item}" for item in archived_files])
        return summary