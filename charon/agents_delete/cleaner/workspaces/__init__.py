"""
charon/agents/cleaner/workspaces/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Workspace management domain module for The Cleaner.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.intent import DynamicActionPayload
from .deleter import WorkspaceDeleter
from .git_ops import WorkspaceGitHandler
from .inspector import WorkspaceInspector
from .scaffolder import WorkspaceScaffolder


class WorkspaceManager:
    """Facade class unifying workspace management domains while maintaining backwards compatibility."""

    def __init__(self, default_projects_dir: Path):
        self.default_projects_dir = default_projects_dir
        self.inspector = WorkspaceInspector(default_projects_dir)
        self.scaffolder = WorkspaceScaffolder(default_projects_dir)
        self.git_handler = WorkspaceGitHandler(default_projects_dir)
        self.deleter = WorkspaceDeleter(default_projects_dir)

    def list_workspaces(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Delegates workspace indexing and inspection to WorkspaceInspector."""
        return self.inspector.list_workspaces(payload, params, raw_prompt)

    def initialize_project_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Delegates project scaffolding to WorkspaceScaffolder."""
        return self.scaffolder.initialize_project_workspace(
            payload, params, raw_prompt
        )

    def commit_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Delegates Git commits to WorkspaceGitHandler."""
        return self.git_handler.commit_workspace(payload, params, raw_prompt)

    def delete_project_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Delegates safe workspace purging to WorkspaceDeleter."""
        return self.deleter.delete_project_workspace(
            payload, params, raw_prompt
        )