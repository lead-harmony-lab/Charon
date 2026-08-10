"""Plugin entrypoint module for cleaner_workspace_scaffolder."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.workspaces.scaffolder import WorkspaceScaffolder

logger = logging.getLogger("CHAROND.Skills.CleanerWorkspaceScaffolder")


def handle_initialize_project_workspace(
    params: Dict[str, Any], default_projects_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Scaffolds directory tree and initializes optional Git repo."""
    projects_path = Path(default_projects_dir) if default_projects_dir else Path.cwd()
    scaffolder = WorkspaceScaffolder(default_projects_dir=projects_path)
    result = scaffolder.initialize_project_workspace(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    default_projects_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for workspace scaffolding operations."""
    if action_name == "initialize_project_workspace":
        return handle_initialize_project_workspace(params, default_projects_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_workspace_scaffolder'."
    )