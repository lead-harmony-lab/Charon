"""
charon/agents/cleaner/workspaces/scaffolder.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Scaffolding domain for initializing Cleaner workspaces.
Updated for DynamicActionPayload intent parsing.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.cleaner.utils import get_param
from charon.intent import DynamicActionPayload
from charon.tools.git import git_init

logger = logging.getLogger("CHAROND.Cleaner.Workspaces.Scaffolder")


class WorkspaceScaffolder:
    """Handles directory structure scaffolding and initial Git setup."""

    def __init__(self, default_projects_dir: Path):
        self.default_projects_dir = default_projects_dir

    def initialize_project_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Scaffolds a new mechatronics project directory and initializes Git."""
        params = params or {}
        base_path_str = get_param(payload, params, "base_path", "target_path", "path")
        raw_name = get_param(payload, params, "project_name", "name")

        if raw_name and ("/" in str(raw_name) or "\\" in str(raw_name)):
            p = Path(str(raw_name)).expanduser()
            raw_name = p.name
            if not base_path_str:
                base_path_str = str(p.parent)

        base_path = (
            Path(str(base_path_str)).expanduser().resolve()
            if base_path_str
            else self.default_projects_dir
        )

        if not raw_name or not str(raw_name).strip():
            logger.error(
                "No project name provided. Refusing to scaffold in root directory."
            )
            return "Execution aborted: Missing 'project_name' parameter for initialization."

        project_name = str(raw_name).strip()

        try:
            target_path = (base_path / project_name).resolve()

            raw_subdirs = get_param(payload, params, "subdirectories")
            if isinstance(raw_subdirs, list):
                subdirs = [str(s) for s in raw_subdirs]
            elif isinstance(raw_subdirs, str):
                subdirs = [
                    s.strip() for s in raw_subdirs.split(",") if s.strip()
                ]
            else:
                subdirs = ["cad", "firmware", "docs", "src", "bom"]

            raw_git = get_param(payload, params, "initialize_git", default=True)
            initialize_git = (
                str(raw_git).lower() in ("true", "1", "yes")
                if not isinstance(raw_git, bool)
                else raw_git
            )

            target_path.mkdir(parents=True, exist_ok=True)
            created_dirs = []

            for sub in subdirs:
                sub_path = target_path / sub.strip("/")
                sub_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(sub)
                (sub_path / ".gitkeep").touch(exist_ok=True)

            msg = (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action         : Workspace Initialization Completed\n"
                f"Target Path    : {target_path}\n"
                f"Subdirectories : {', '.join(created_dirs)}"
            )

            if initialize_git:
                if not (target_path / ".git").exists():
                    _, status_msg = git_init(target_path)
                    msg += f"\nGit Repo       : {status_msg}"

            return msg

        except PermissionError:
            logger.error(
                f"Permission denied attempting to scaffold at {base_path}"
            )
            return f"Execution aborted: Permission denied writing to {base_path}."
        except Exception as e:
            logger.error(
                f"The Cleaner encountered an error during initialization: {e}"
            )
            return f"An unexpected error occurred during initialization: {e}"