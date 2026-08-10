"""
charon/core/workspace.py
System Version: v0.3.3 | File Revision: 2.0.0

Module: Isolated Task Workspace Manager.
Manages scoped directory sandboxes for execution tasks, preventing directory traversal
and cross-task workspace leaks adhering strictly to the Janitorial Working Anchor.
"""

import logging
from pathlib import Path
import shutil
from typing import List, Optional, Union

try:
    from charon.config.paths import DATA_DIR
except ImportError:
    from charon.config import DATA_DIR

logger = logging.getLogger("Charon.Core.Workspace")


class WorkspaceSecurityError(PermissionError):
    """Raised when a workspace operation attempts to escape its directory sandbox boundary."""
    pass


class WorkspaceManager:
    """Manages scoped task directory creation, file staging, and path isolation."""

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir: Path = (root_dir or (DATA_DIR / "workspaces")).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[WORKSPACE] Initialized sandbox root at: {self.root_dir}")

    def get_task_workspace(self, task_id: str, create: bool = True) -> Path:
        """
        Returns the absolute path for a task's workspace.
        Ensures the directory exists and stays within root boundary.
        """
        safe_task_id = "".join(c for c in str(task_id) if c.isalnum() or c in ("_", "-"))
        if not safe_task_id:
            raise ValueError(f"Invalid task_id string for workspace creation: '{task_id}'")

        workspace_path = (self.root_dir / safe_task_id).resolve()

        # Verify workspace remains strictly inside root_dir and is not root_dir itself
        self._verify_path_contained(workspace_path, boundary=self.root_dir)
        if workspace_path == self.root_dir:
            raise WorkspaceSecurityError("Task workspace cannot be identical to root sandbox directory.")

        if create:
            workspace_path.mkdir(parents=True, exist_ok=True)

        return workspace_path

    def _verify_path_contained(self, target_path: Path, boundary: Optional[Path] = None) -> None:
        """Guards against directory traversal by verifying target is inside the specified boundary."""
        limit = boundary.resolve() if boundary else self.root_dir
        resolved = target_path.resolve()

        try:
            resolved.relative_to(limit)
        except ValueError:
            raise WorkspaceSecurityError(
                f"Path traversal blocked: '{target_path}' escapes workspace boundary '{limit}'"
            )

    def write_file(self, task_id: str, relative_filename: str, content: Union[str, bytes]) -> Path:
        """Write text or bytes content safely into a file within the task's isolated workspace."""
        workspace = self.get_task_workspace(task_id, create=True)
        target_path = (workspace / relative_filename).resolve()

        # Enforce boundary containment strictly against THIS task's workspace
        self._verify_path_contained(target_path, boundary=workspace)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        with open(target_path, mode, encoding=encoding) as f:
            f.write(content)

        logger.debug(f"[WORKSPACE] Wrote file in workspace '{task_id}': {relative_filename}")
        return target_path

    def read_file(self, task_id: str, relative_filename: str) -> str:
        """Read text file safely from within a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        target_path = (workspace / relative_filename).resolve()

        self._verify_path_contained(target_path, boundary=workspace)

        if not target_path.exists():
            raise FileNotFoundError(
                f"File '{relative_filename}' not found in task workspace '{task_id}'"
            )

        return target_path.read_text(encoding="utf-8")

    def read_bytes(self, task_id: str, relative_filename: str) -> bytes:
        """Read binary file safely from within a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        target_path = (workspace / relative_filename).resolve()

        self._verify_path_contained(target_path, boundary=workspace)

        if not target_path.exists():
            raise FileNotFoundError(
                f"File '{relative_filename}' not found in task workspace '{task_id}'"
            )

        return target_path.read_bytes()

    def file_exists(self, task_id: str, relative_filename: str) -> bool:
        """Checks if a file exists within a task workspace without throwing an exception."""
        try:
            workspace = self.get_task_workspace(task_id, create=False)
            target_path = (workspace / relative_filename).resolve()
            self._verify_path_contained(target_path, boundary=workspace)
            return target_path.exists() and target_path.is_file()
        except Exception:
            return False

    def list_files(self, task_id: str) -> List[Path]:
        """List all relative file paths inside a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        if not workspace.exists():
            return []

        return [
            p.relative_to(workspace)
            for p in workspace.rglob("*")
            if p.is_file()
        ]

    def cleanup_workspace(self, task_id: str) -> bool:
        """Delete task workspace directory and all contained assets."""
        try:
            workspace = self.get_task_workspace(task_id, create=False)
            if workspace.exists():
                shutil.rmtree(workspace)
                logger.info(f"[WORKSPACE] Purged task workspace directory for '{task_id}'")
                return True
            return False
        except Exception as e:
            logger.error(f"[WORKSPACE] Failed to cleanup task workspace for '{task_id}': {e}")
            return False