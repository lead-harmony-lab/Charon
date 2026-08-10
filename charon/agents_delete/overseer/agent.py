"""
charon/agents/overseer/agent.py
System Version: v0.1.0 | File Revision: 2.3.0

Module: System maintenance and health diagnostics agent (The Overseer).
Inherits from BaseAgent for unified system probing and capability discovery. Updated for dynamic intent schemas.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.overseer.assets import prune_orphaned_assets
from charon.agents.overseer.constants import (
    ACTION_MAP,
    VALID_OVERSEER_ACTIONS,
)
from charon.agents.overseer.databases import optimize_sqlite_db
from charon.agents.overseer.gaps import resolve_skill_gaps
from charon.agents.overseer.pruning import (
    prune_logs_and_cache,
    prune_stale_workspaces,
)
from charon.agents.overseer.resource_guard import audit_resource_guard
from charon.agents.overseer.telemetry import get_system_health
from charon.agents.overseer.vector_store import audit_vector_store
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.overseer")


class TheOverseer(BaseAgent):
    """Agent responsible for background maintenance, database optimization, health telemetry, log/workspace pruning, and resource guarding."""

    name: str = "TheOverseer"
    domain: str = (
        "Background maintenance, database optimization, log and workspace pruning, "
        "asset cleanup, health telemetry, resource threshold enforcement, and skill gap resolution."
    )
    description: str = (
        "System maintenance and health diagnostics agent responsible for SQLite database "
        "optimization, vector store auditing, log/cache/workspace pruning, orphaned asset cleanup, "
        "host telemetry, resource threshold enforcement, and automated skill gap resolution."
    )

    system_requirements: List[str] = []
    consumed_artifacts: List[str] = [
        "target_db",
        "prune_days",
        "workspaces_dir",
        "datasheets_dir",
        "disk_warning_pct",
    ]
    produced_artifacts: List[str] = [
        "maintenance_report",
        "system_health",
        "audit_report",
        "resource_guard_report",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "optimize_databases": [
            "optimize_databases",
            "optimize_db",
            "vacuum",
            "optimize",
        ],
        "audit_vector_store": [
            "audit_vector_store",
            "audit_vectors",
            "audit_chroma",
        ],
        "prune_logs_and_cache": [
            "prune_logs_and_cache",
            "prune_logs",
            "clear_cache",
            "prune_cache",
        ],
        "prune_stale_workspaces": [
            "prune_stale_workspaces",
            "prune_workspaces",
            "clean_workspaces",
            "sweep_workspaces",
        ],
        "prune_orphaned_assets": [
            "prune_orphaned_assets",
            "prune_assets",
            "clean_orphans",
        ],
        "get_system_health": [
            "get_system_health",
            "health",
            "system_health",
            "telemetry",
        ],
        "audit_resource_guard": [
            "audit_resource_guard",
            "check_resources",
            "resource_guard",
            "enforce_resource_guard",
        ],
        "resolve_skill_gaps": [
            "resolve_skill_gaps",
            "fix_gaps",
            "resolve_gaps",
        ],
        "run_full_maintenance": [
            "run_full_maintenance",
            "full_maintenance",
            "maintenance",
            "run_maintenance",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheOverseer maintenance agent with optional database path targeting."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.db_path = Path(db_path).resolve() if db_path else None
        logger.info(f"[{self.name}] Initialized with DB path target: {self.db_path or 'Default/Auto'}")

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying database path configuration and environment readiness."""
        base_health = super().health_check()
        try:
            db_configured = self.db_path is not None
            db_exists = self.db_path.exists() if db_configured else True
            healthy = db_exists and base_health.get("healthy", True)
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": "Operational" if healthy else "Degraded: Specified target database does not exist",
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
                    "db_path": str(self.db_path) if self.db_path else "Default/Auto",
                    "db_exists": db_exists,
                    **base_health.get("details", {}),
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
                    "db_path": str(self.db_path) if getattr(self, "db_path", None) else None,
                },
            }

    async def optimize_sqlite_db(
        self, target_db: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """Runs SQLite PRAGMA and VACUUM optimizations on target databases."""
        return await optimize_sqlite_db(
            default_db_path=self.db_path, target_db=target_db
        )

    async def audit_vector_store(self) -> Dict[str, Any]:
        """Asynchronously audits the vector store."""
        return await audit_vector_store()

    async def prune_logs_and_cache(
        self, prune_days: int = 7
    ) -> Dict[str, Any]:
        """Asynchronously prunes old logs and cache files."""
        return await prune_logs_and_cache(prune_days=prune_days)

    async def prune_stale_workspaces(
        self,
        prune_days: int = 7,
        workspaces_dir: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Asynchronously prunes stale task sandboxes and workspace artifacts."""
        return await prune_stale_workspaces(
            prune_days=prune_days, workspaces_dir=workspaces_dir
        )

    async def prune_orphaned_assets(
        self, datasheets_dir: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """Asynchronously sweeps workspace directories for broken symlinks or unlinked assets."""
        return await prune_orphaned_assets(datasheets_dir=datasheets_dir)

    async def get_system_health(self) -> Dict[str, Any]:
        """Asynchronously fetches host telemetry and health metrics."""
        return await get_system_health()

    async def audit_resource_guard(self) -> Dict[str, Any]:
        """Asynchronously audits process memory, disk utilization, and system limits."""
        return await audit_resource_guard()

    async def resolve_skill_gaps(self) -> Dict[str, Any]:
        """Asynchronously resolves pending skill gaps using charon-forge."""
        return await resolve_skill_gaps()

    async def execute(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatches maintenance commands for DynamicActionPayload actions."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        self.report_progress(
            message=f"Executing overseer action: '{normalized_action}'",
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
                if normalized_action in VALID_OVERSEER_ACTIONS
                else "get_system_health"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        target_action = payload.call_action or normalized_action

        logger.info(
            f"[{self.name}] Executing action '{target_action}' with params: {payload.params}"
        )

        target_db = payload.params.get("target_db") or raw_params.get("target_db")
        prune_days = payload.params.get("prune_days", raw_params.get("prune_days", 7))
        workspaces_dir = payload.params.get("workspaces_dir") or raw_params.get("workspaces_dir")
        datasheets_dir = payload.params.get("datasheets_dir") or raw_params.get("datasheets_dir")

        try:
            if target_action == "optimize_databases":
                result = await self.optimize_sqlite_db(target_db=target_db)

            elif target_action == "audit_vector_store":
                result = await self.audit_vector_store()

            elif target_action == "prune_logs_and_cache":
                result = await self.prune_logs_and_cache(prune_days=prune_days)

            elif target_action == "prune_stale_workspaces":
                result = await self.prune_stale_workspaces(
                    prune_days=prune_days, workspaces_dir=workspaces_dir
                )

            elif target_action == "prune_orphaned_assets":
                result = await self.prune_orphaned_assets(
                    datasheets_dir=datasheets_dir
                )

            elif target_action == "get_system_health":
                result = await self.get_system_health()

            elif target_action == "audit_resource_guard":
                result = await self.audit_resource_guard()

            elif target_action == "resolve_skill_gaps":
                result = await self.resolve_skill_gaps()

            elif target_action == "run_full_maintenance":
                db_res = await self.optimize_sqlite_db(target_db=target_db)
                vec_res = await self.audit_vector_store()
                prune_res = await self.prune_logs_and_cache(prune_days=prune_days)
                ws_res = await self.prune_stale_workspaces(
                    prune_days=prune_days, workspaces_dir=workspaces_dir
                )
                asset_res = await self.prune_orphaned_assets(
                    datasheets_dir=datasheets_dir
                )
                res_guard_res = await self.audit_resource_guard()
                gap_res = await self.resolve_skill_gaps()
                health_res = await self.get_system_health()
                result = {
                    "action": "run_full_maintenance",
                    "status": "completed",
                    "database_optimization": db_res,
                    "vector_store_audit": vec_res,
                    "log_cache_prune": prune_res,
                    "workspace_prune": ws_res,
                    "orphaned_asset_prune": asset_res,
                    "resource_guard_audit": res_guard_res,
                    "skill_gap_resolution": gap_res,
                    "system_health": health_res,
                }

            else:
                raise ValueError(f"Unknown Overseer action: '{target_action}'")

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