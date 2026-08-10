"""
charon/agents/cleaner/workspaces/git_ops.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Git operations domain for Cleaner workspaces.
Updated for DynamicActionPayload intent parsing.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.cleaner.utils import get_param, resolve_target_workspace
from charon.intent import DynamicActionPayload
from charon.tools.git import git_commit

logger = logging.getLogger("CHAROND.Cleaner.Workspaces.GitOps")


class WorkspaceGitHandler:
    """Handles Git operations such as commits and workspace state tracking."""

    def __init__(self, default_projects_dir: Path):
        self.default_projects_dir = default_projects_dir

    def commit_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Stages all changes and commits them to the local Git repository."""
        params = params or {}
        target_path_str = get_param(
            payload, params, "target_path", "base_path", "path", "project_directory"
        )
        project_name = get_param(payload, params, "project_name", "name")
        commit_message = str(
            get_param(
                payload,
                params,
                "commit_message",
                "message",
                default="Automated routine commit by Charon.",
            )
        ).strip()

        try:
            target_path, err_msg = resolve_target_workspace(
                target_path_str, project_name, self.default_projects_dir
            )

            if err_msg or not target_path or not target_path.exists():
                return (
                    f"[SYSTEM EXECUTION REPORT]\n"
                    f"Action : Git Commit\n"
                    f"Status : Failed\n"
                    f"Reason : Workspace target path '{target_path}' does not exist or is invalid."
                )

            _, status_code, result = git_commit(target_path, commit_message)

            if status_code in ("no_git", "no_exe"):
                return result
            elif status_code == "clean":
                return (
                    f"[SYSTEM EXECUTION REPORT]\n"
                    f"Action : Git Commit\n"
                    f"Target : {target_path}\n"
                    f"Status : Skipped (Workspace is already clean)"
                )
            elif status_code == "committed":
                return (
                    f"[SYSTEM EXECUTION REPORT]\n"
                    f"Action  : Git Commit Completed\n"
                    f"Target  : {target_path}\n"
                    f"Message : '{commit_message}'"
                )
            else:
                return (
                    f"[SYSTEM EXECUTION REPORT]\n"
                    f"Action : Git Commit\n"
                    f"Status : Failed\n"
                    f"Reason : {result}"
                )
        except Exception as e:
            logger.error(f"Error during commit_workspace execution: {e}")
            return (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action : Git Commit\n"
                f"Status : Failed\n"
                f"Reason : {e}"
            )