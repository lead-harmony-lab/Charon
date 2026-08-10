"""Plugin entrypoint module for cleaner_workspace_deleter."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.workspaces.deleter import WorkspaceDeleter

logger = logging.getLogger("CHAROND.Skills.CleanerWorkspaceDeleter")


def handle_delete_project_workspace(
    params: Dict[str, Any], default_projects_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Purges project workspace directory following confirmation safety checks."""
    projects_path = Path(default_projects_dir) if default_projects_dir else Path.cwd()
    deleter = WorkspaceDeleter(default_projects_dir=projects_path)
    result = deleter.delete_project_workspace(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    default_projects_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for workspace deletion operations."""
    if action_name == "delete_project_workspace":
        return handle_delete_project_workspace(params, default_projects_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_workspace_deleter'."
    )