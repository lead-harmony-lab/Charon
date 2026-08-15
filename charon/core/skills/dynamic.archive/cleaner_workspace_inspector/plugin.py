"""Plugin entrypoint module for cleaner_workspace_inspector."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.workspaces.inspector import WorkspaceInspector

logger = logging.getLogger("CHAROND.Skills.CleanerWorkspaceInspector")


def handle_list_workspaces(
    params: Dict[str, Any], default_projects_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Lists or inspects active project workspaces."""
    projects_path = Path(default_projects_dir) if default_projects_dir else Path.cwd()
    inspector = WorkspaceInspector(default_projects_dir=projects_path)
    result = inspector.list_workspaces(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    default_projects_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for workspace inspection operations."""
    if action_name == "list_workspaces":
        return handle_list_workspaces(params, default_projects_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_workspace_inspector'."
    )