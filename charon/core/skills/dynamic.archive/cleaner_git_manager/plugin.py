"""Plugin entrypoint module for cleaner_git_manager."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.workspaces.git_ops import WorkspaceGitHandler

logger = logging.getLogger("CHAROND.Skills.CleanerGitManager")


def handle_commit_workspace(
    params: Dict[str, Any], default_projects_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Stages workspace changes and executes git commit."""
    projects_path = Path(default_projects_dir) if default_projects_dir else Path.cwd()
    git_handler = WorkspaceGitHandler(default_projects_dir=projects_path)
    result = git_handler.commit_workspace(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    default_projects_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for Git management operations."""
    if action_name == "commit_workspace":
        return handle_commit_workspace(params, default_projects_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_git_manager'."
    )