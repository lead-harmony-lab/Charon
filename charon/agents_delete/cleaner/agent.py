"""
charon/agents/cleaner/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: agents/cleaner/agent.py - Specialist Agent: Workspace Hygiene for Charon.

Manages workspace directory scaffolding, log pruning, file archiving, CAD version
sweeping, and Git operations. Inherits from BaseAgent for unified system probing,
telemetry instrumentation, and capability discovery. Updated for dynamic intent schemas.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.cleaner.cad import CADManager
from charon.agents.cleaner.logs import LogManager
from charon.agents.cleaner.workspaces import WorkspaceManager
from charon.config.paths import LOGS_DIR, PROJECTS_DIR, ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.cleaner")

VALID_CLEANER_ACTIONS = (
    "initialize_project_workspace",
    "commit_workspace",
    "sweep_cad_iterations",
    "list_workspaces",
    "prune_logs",
    "delete_project_workspace",
)

ACTION_MAP = {
    "init": "initialize_project_workspace",
    "scaffold": "initialize_project_workspace",
    "create_workspace": "initialize_project_workspace",
    "initialize_workspace": "initialize_project_workspace",
    "initialize_project_workspace": "initialize_project_workspace",
    "commit": "commit_workspace",
    "git_commit": "commit_workspace",
    "commit_workspace": "commit_workspace",
    "sweep": "sweep_cad_iterations",
    "sweep_cad": "sweep_cad_iterations",
    "clean_cad": "sweep_cad_iterations",
    "sweep_cad_iterations": "sweep_cad_iterations",
    # --- INSPECT & LIST ALIASES ---
    "list": "list_workspaces",
    "list_projects": "list_workspaces",
    "workspaces": "list_workspaces",
    "list_workspaces": "list_workspaces",
    "inspect": "list_workspaces",
    "inspect_workspace": "list_workspaces",
    "examine": "list_workspaces",
    "check": "list_workspaces",
    # -------------------------------
    "prune": "prune_logs",
    "clean_logs": "prune_logs",
    "clear_logs": "prune_logs",
    "sweep_logs": "prune_logs",
    "prune_logs": "prune_logs",
    "delete": "delete_project_workspace",
    "purge": "delete_project_workspace",
    "remove_workspace": "delete_project_workspace",
    "delete_project_workspace": "delete_project_workspace",
}


class TheCleaner(BaseAgent):
    """Specialist Agent: Workspace Hygiene.

    Domain: Directory management, log maintenance, file archiving, CAD version
    sweeping, and Git version control.
    """

    name: str = "TheCleaner"
    domain: str = "Directory management, log maintenance, file archiving, CAD version sweeping, and Git version control"
    description: str = "Manages workspace scaffolding, log pruning, CAD version sweeping, and Git repository operations."

    system_requirements: List[str] = ["git"]
    consumed_artifacts: List[str] = ["workspace_path", "cad_file", "log_directory"]
    produced_artifacts: List[str] = ["workspace_structure", "git_commit_hash", "pruned_log_summary"]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "initialize_project_workspace": [
            "initialize_project_workspace",
            "init",
            "scaffold",
            "create_workspace",
            "initialize_workspace",
        ],
        "commit_workspace": ["commit_workspace", "commit", "git_commit"],
        "sweep_cad_iterations": [
            "sweep_cad_iterations",
            "sweep",
            "sweep_cad",
            "clean_cad",
        ],
        "list_workspaces": [
            "list_workspaces",
            "list",
            "list_projects",
            "workspaces",
            "inspect",
            "inspect_workspace",
            "examine",
            "check",
        ],
        "prune_logs": [
            "prune_logs",
            "prune",
            "clean_logs",
            "clear_logs",
            "sweep_logs",
        ],
        "delete_project_workspace": [
            "delete_project_workspace",
            "delete",
            "purge",
            "remove_workspace",
        ],
    }

    # BaseAgent capability registration
    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        default_projects_dir: Optional[Union[str, Path]] = None,
        default_logs_dir: Optional[Union[str, Path]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheCleaner agent, binding directories and the SkillLibrarian base."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.default_projects_dir = (
            Path(default_projects_dir).resolve()
            if default_projects_dir
            else PROJECTS_DIR
        )
        self.default_logs_dir = (
            Path(default_logs_dir).resolve()
            if default_logs_dir
            else LOGS_DIR
        )

        self.workspace_mgr = WorkspaceManager(self.default_projects_dir)
        self.cad_mgr = CADManager(self.default_projects_dir)
        self.log_mgr = LogManager(self.default_logs_dir)

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying workspace/log directories and system binary requirements."""
        base_health = super().health_check()
        try:
            projects_ok = self.default_projects_dir.exists()
            logs_ok = self.default_logs_dir.exists()
            directories_ok = projects_ok and logs_ok

            is_healthy = base_health["status"] == "healthy" and directories_ok
            status_msg = (
                "Operational"
                if is_healthy
                else f"Degraded: missing_deps={base_health.get('missing_dependencies', [])}, directories_ok={directories_ok}"
            )
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": is_healthy,
                "status": status_msg,
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
                    "projects_dir": str(self.default_projects_dir),
                    "projects_dir_exists": projects_ok,
                    "logs_dir": str(self.default_logs_dir),
                    "logs_dir_exists": logs_ok,
                },
                "dynamic_skills_available": base_health.get("dynamic_skills_available", []),
                "native_actions_supported": base_health.get("native_actions_supported", []),
            }
        except Exception as e:
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": False,
                "status": f"Degraded: Exception during health check ({e})",
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
                    "projects_dir": str(self.default_projects_dir),
                    "logs_dir": str(self.default_logs_dir),
                },
            }

    def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Cleaner's capabilities, validated against DynamicActionPayload."""
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            payload_dict = dict(parameters) if parameters else {}
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        # Reject unmapped / invalid actions before fallback construction
        if normalized_action not in VALID_CLEANER_ACTIONS:
            logger.error(f"[{self.name}] Does not recognize action: {action}")
            err_msg = f"Unknown action '{action}' for agent {self.name}"
            self.report_trace(
                event_type="EXECUTION_ERROR",
                action=action_clean,
                details={"error": err_msg},
            )
            raise ValueError(err_msg)

        payload_dict = dict(parameters) if parameters else {}

        if raw_prompt and not any(
            payload_dict.get(k)
            for k in [
                "project_name",
                "name",
                "target_path",
                "base_path",
                "project_directory",
            ]
        ):
            payload_dict["query"] = raw_prompt.strip()

        self.report_progress(
            message=f"Executing workspace hygiene action: '{normalized_action}'",
            phase="START",
            action=normalized_action,
            progress_pct=0.0,
        )
        self.report_trace(
            event_type="EXECUTION_START",
            action=normalized_action,
            details={"parameters": payload_dict, "raw_prompt": raw_prompt},
        )
        self.report_action(action=normalized_action, details=payload_dict)

        try:
            if "call_action" in payload_dict and "params" in payload_dict:
                payload = DynamicActionPayload.model_validate(payload_dict)
            else:
                extracted_params = {
                    k: v for k, v in payload_dict.items()
                    if k not in ["call_action", "action", "thought", "memory_candidate"]
                }
                payload = DynamicActionPayload(
                    call_action=normalized_action,
                    thought=payload_dict.get("thought", ""),
                    params=extracted_params,
                )
        except Exception as e:
            logger.warning(
                f"[{self.name}] Payload validation warning ({e}). Executing fallback construction..."
            )
            fallback_action = (
                normalized_action
                if normalized_action in VALID_CLEANER_ACTIONS
                else "list_workspaces"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        try:
            target_action = payload.call_action or normalized_action

            if target_action == "initialize_project_workspace":
                result = self.workspace_mgr.initialize_project_workspace(
                    payload, parameters, raw_prompt
                )
            elif target_action == "commit_workspace":
                result = self.workspace_mgr.commit_workspace(
                    payload, parameters, raw_prompt
                )
            elif target_action == "sweep_cad_iterations":
                result = self.cad_mgr.sweep_cad_iterations(
                    payload, parameters, raw_prompt
                )
            elif target_action == "list_workspaces":
                result = self.workspace_mgr.list_workspaces(
                    payload, parameters, raw_prompt
                )
            elif target_action == "prune_logs":
                result = self.log_mgr.prune_logs(
                    payload, parameters, raw_prompt
                )
            elif target_action == "delete_project_workspace":
                result = self.workspace_mgr.delete_project_workspace(
                    payload, parameters, raw_prompt
                )
            else:
                logger.error(f"[{self.name}] Does not recognize action: {action}")
                raise ValueError(f"Unknown action '{action}'")

            self.report_progress(
                message=f"Successfully completed action: '{normalized_action}'",
                phase="COMPLETE",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_COMPLETE",
                action=normalized_action,
                details={"status": "success"},
            )
            return result

        except Exception as e:
            logger.exception(f"[{self.name}] Execution error during '{normalized_action}': {e}")
            self.report_progress(
                message=f"Failed to execute action: '{normalized_action}'",
                phase="ERROR",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_ERROR",
                action=normalized_action,
                details={"error": str(e)},
            )
            raise

    # =========================================================================
    # BACKWARD COMPATIBILITY DELEGATE ALIASES
    # =========================================================================

    def _prune_logs(self, payload=None, params=None, raw_prompt=""):
        return self.log_mgr.prune_logs(payload, params, raw_prompt)

    def _list_workspaces(self, payload=None, params=None, raw_prompt=""):
        return self.workspace_mgr.list_workspaces(payload, params, raw_prompt)

    def _initialize_project_workspace(self, payload=None, params=None, raw_prompt=""):
        return self.workspace_mgr.initialize_project_workspace(payload, params, raw_prompt)

    def _commit_workspace(self, payload=None, params=None, raw_prompt=""):
        return self.workspace_mgr.commit_workspace(payload, params, raw_prompt)

    def _sweep_cad_iterations(self, payload=None, params=None, raw_prompt=""):
        return self.cad_mgr.sweep_cad_iterations(payload, params, raw_prompt)

    def _delete_project_workspace(self, payload=None, params=None, raw_prompt=""):
        return self.workspace_mgr.delete_project_workspace(payload, params, raw_prompt)