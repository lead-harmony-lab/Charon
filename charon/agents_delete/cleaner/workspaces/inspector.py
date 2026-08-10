"""
charon/agents/cleaner/workspaces/inspector.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Inspection and listing domain for Cleaner workspaces.
Updated for DynamicActionPayload intent parsing.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.agents.cleaner.utils import get_param, resolve_target_workspace
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Cleaner.Workspaces.Inspector")

# Extension map for intelligent CAD/Asset/Code workspace profiling
FILE_TYPE_MAP = {
    ".fcstd": "FreeCAD Design Models",
    ".stl": "3D Printable Meshes (STL)",
    ".step": "STEP CAD Assemblies",
    ".stp": "STEP CAD Assemblies",
    ".3mf": "3D Manufacturing Format",
    ".scad": "OpenSCAD Code",
    ".py": "Python Scripts",
    ".json": "JSON Configuration Files",
    ".yaml": "YAML Configuration Files",
    ".yml": "YAML Configuration Files",
    ".sh": "Shell Scripts",
    ".md": "Markdown Documentation",
    ".txt": "Text Notes",
    ".cpp": "C++ Source Code",
    ".hpp": "C++ Headers",
    ".c": "C Source Code",
    ".h": "C Headers",
    ".ino": "Arduino Sketches",
}


class WorkspaceInspector:
    """Handles directory inspection, heuristic profiling, and workspace listing."""

    def __init__(self, default_projects_dir: Path):
        self.default_projects_dir = default_projects_dir

    def list_workspaces(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Indexes active project directories or inspects a specific target workspace in detail."""
        params = params or {}
        target_path_str = get_param(
            payload, params, "target_path", "base_path", "path", "project_directory"
        )
        project_name = get_param(payload, params, "project_name", "name")

        target_path: Optional[Path] = None
        if target_path_str or project_name:
            try:
                target_path, _ = resolve_target_workspace(
                    target_path_str, project_name, self.default_projects_dir
                )
            except Exception as err:
                logger.warning(f"Failed to resolve workspace path: {err}")
                target_path = None

        if (not target_path or target_path == self.default_projects_dir) and raw_prompt:
            path_matches = re.findall(r"(?:~/|/)[A-Za-z0-9_\-./]+", raw_prompt)
            for pm in path_matches:
                clean_pm = pm.rstrip(".:,;'\")")
                resolved = Path(clean_pm).expanduser().resolve()
                if resolved.exists():
                    target_path = resolved
                    break

            if (
                (not target_path or target_path == self.default_projects_dir)
                and self.default_projects_dir.exists()
            ):
                for token in raw_prompt.split():
                    clean_token = token.strip(" '\"`./,;:()")
                    if clean_token:
                        candidate = (self.default_projects_dir / clean_token).resolve()
                        if candidate.exists() and candidate.is_dir():
                            target_path = candidate
                            break

        if not target_path:
            target_path = self.default_projects_dir

        if (
            target_path.exists()
            and target_path.is_dir()
            and target_path != self.default_projects_dir
        ):
            return self._inspect_single_workspace(target_path)

        try:
            if not target_path.exists() or not target_path.is_dir():
                return f"The workspace directory {target_path} does not exist or is inaccessible."

            exclusions = {
                "Tools",
                "Downloads",
                "Desktop",
                "archive",
                "node_modules",
                ".git",
            }

            projects = [
                item.name
                for item in target_path.iterdir()
                if item.is_dir()
                and not item.name.startswith(".")
                and item.name not in exclusions
            ]

            if not projects:
                return f"No active projects found in {target_path}."

            projects.sort()

            output = f"Current active projects located in {target_path}:\n"
            output += "\n".join([f" • {proj}" for proj in projects])

            return output.strip()

        except PermissionError:
            logger.error(f"Permission denied reading {target_path}")
            return f"Execution aborted: Permission denied reading {target_path}."
        except Exception as e:
            logger.error(f"Error scanning workspaces: {e}")
            return f"An unexpected error occurred while scanning for projects: {e}"

    def _inspect_single_workspace(self, workspace_path: Path) -> str:
        """Inspects a specific project directory, reading documentation or generating a heuristic summary."""
        path = workspace_path.resolve()

        if not path.exists():
            return f"Directory `{path}` does not exist."
        if not path.is_dir():
            return f"Path `{path}` is a file, not a directory."

        doc_files = (
            list(path.glob("README*"))
            + list(path.glob("NOTES*"))
            + list(path.glob("*.md"))
        )

        if doc_files:
            readme = doc_files[0]
            try:
                content = readme.read_text(encoding="utf-8", errors="replace")[:1200]
                return (
                    f"### Workspace Inspection: `{path.name}`\n"
                    f"**Path**: `{path}`\n\n"
                    f"#### Documentation (`{readme.name}`):\n"
                    f"{content}"
                )
            except Exception as err:
                logger.warning(f"Failed to read doc file {readme}: {err}")

        try:
            items = list(path.iterdir())
            subdirs = [
                i.name for i in items if i.is_dir() and not i.name.startswith(".")
            ]
            files = [
                i for i in items if i.is_file() and not i.name.startswith(".")
            ]

            if not items:
                return f"The workspace directory `{path.name}` is currently empty."

            ext_counts: Dict[str, int] = {}
            for f in files:
                ext = f.suffix.lower() or "no_extension"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

            breakdown: List[str] = []
            for ext, count in ext_counts.items():
                label = FILE_TYPE_MAP.get(ext, f"{ext.upper()} Files")
                breakdown.append(f" • {label}: {count} file(s)")

            summary = [
                f"### Workspace Inspection: `{path.name}`",
                f"**Path**: `{path}`",
                "",
                "**Overview**: No explicit README or notes file found. Inferred project structure:",
            ]

            if breakdown:
                summary.append("\n**File Contents**:")
                summary.extend(breakdown)

            if subdirs:
                summary.append(
                    f"\n**Subdirectories ({len(subdirs)})**: "
                    + ", ".join([f"`{d}`" for d in subdirs])
                )

            return "\n".join(summary)

        except Exception as e:
            logger.error(f"Error inspecting workspace {path}: {e}")
            return f"An unexpected error occurred while inspecting `{path}`: {e}"