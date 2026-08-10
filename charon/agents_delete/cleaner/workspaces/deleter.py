"""
charon/agents/cleaner/workspaces/deleter.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Deletion safety and purging domain for Cleaner workspaces.
Updated for DynamicActionPayload integration and safe authorization checking.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.cleaner.utils import get_param
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Cleaner.Workspaces.Deleter")


class WorkspaceDeleter:
    """Handles safety checks, authorization validation, and permanent deletion of workspaces."""

    def __init__(self, default_projects_dir: Path):
        self.default_projects_dir = default_projects_dir

    def delete_project_workspace(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Permanently purges a project workspace directory from disk with confirmation safety check."""
        params = params or {}
        base_path_str = get_param(payload, params, "base_path", "target_path", "path")
        raw_project_name = get_param(payload, params, "project_name", "name")
        prompt_text = str(
            get_param(payload, params, "prompt", "raw_prompt", default=raw_prompt)
        ).lower()

        if raw_project_name and ("/" in str(raw_project_name) or "\\" in str(raw_project_name)):
            p = Path(str(raw_project_name)).expanduser()
            raw_project_name = p.name
            if not base_path_str:
                base_path_str = str(p.parent)

        base_path = (
            Path(str(base_path_str)).expanduser().resolve()
            if base_path_str
            else self.default_projects_dir
        )

        project_name = (
            str(raw_project_name).strip() if raw_project_name else None
        )

        if not project_name:
            match = re.search(
                r"(?:project|workspace|called|named)\s+['\"]?([A-Za-z0-9_-]+)['\"]?",
                prompt_text,
                re.IGNORECASE,
            )
            if match:
                project_name = match.group(1)

        if not project_name:
            logger.error("No project name provided for deletion.")
            return "Execution aborted: Missing 'project_name' parameter for deletion."

        try:
            target_path = (base_path / project_name).resolve()

            if target_path == base_path or not target_path.is_relative_to(
                base_path
            ):
                logger.error(
                    f"Safety protocol engaged: Denied attempt to delete {target_path}"
                )
                return f"Execution aborted: Safety protocol prevents deletion of {target_path}."

            if not target_path.exists():
                return f"Deletion skipped: Workspace directory '{target_path}' does not exist."

            p_params = getattr(payload, "params", {}) if isinstance(getattr(payload, "params", None), dict) else {}

            is_confirmed = (
                getattr(payload, "confirmed", False) is True
                or getattr(payload, "authorized", False) is True
                or getattr(payload, "gatekeeper_authorized", False) is True
                or p_params.get("confirmed") is True
                or p_params.get("authorized") is True
                or p_params.get("gatekeeper_authorized") is True
                or params.get("confirmed") is True
                or params.get("authorized") is True
                or params.get("gatekeeper_authorized") is True
                or "proceed" in prompt_text
                or "confirm" in prompt_text
            )

            if not is_confirmed:
                dir_count = sum(
                    1 for p in target_path.rglob("*") if p.is_dir()
                )
                file_count = sum(
                    1 for p in target_path.rglob("*") if p.is_file()
                )

                return (
                    f"[AUTHORIZATION REQUIRED]\n"
                    f"Action Requested : Permanent Workspace Deletion\n"
                    f"Project Name     : {project_name}\n"
                    f"Target Path      : {target_path}\n"
                    f"Target Contents  : {file_count} file(s), {dir_count} folder(s)\n"
                    f"Warning          : This operation cannot be undone.\n\n"
                    f"To proceed with execution, re-submit your instruction including the word 'proceed'."
                )

            file_count = sum(1 for p in target_path.rglob("*") if p.is_file())
            dir_count = sum(1 for p in target_path.rglob("*") if p.is_dir())

            shutil.rmtree(target_path)
            logger.info(f"Workspace permanently purged: {target_path}")

            return (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action   : Workspace Purge\n"
                f"Status   : SUCCESS\n"
                f"Target   : {target_path}\n"
                f"Summary  : Permanently scrubbed {file_count} file(s) and {dir_count} folder(s)."
            )

        except PermissionError:
            logger.error(
                f"Permission denied attempting to purge {target_path}"
            )
            return (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action: Workspace Purge\n"
                f"Status: FAILED\n"
                f"Reason: Permission denied deleting {target_path}."
            )
        except Exception as e:
            logger.error(f"Error purging workspace: {e}")
            return (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action: Workspace Purge\n"
                f"Status: FAILED\n"
                f"Reason: {e}"
            )