"""
charon/agents/quartermaster/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Orchestrator class for logistics and documentation management.
Inherits from BaseAgent for unified system probing and capability discovery.
Updated for dynamic intent schemas.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.quartermaster.bom import generate_bom
from charon.agents.quartermaster.datasheets import fetch_datasheet
from charon.agents.quartermaster.inventory import check_inventory, log_inventory
from charon.config.paths import (
    DATASHEETS_DIR,
    QUARTERMASTER_DB_PATH,
    ensure_ecosystem_directories,
)
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.quartermaster")

VALID_QUARTERMASTER_ACTIONS = (
    "check_inventory",
    "fetch_datasheet",
    "log_inventory",
    "generate_bom",
)

ACTION_MAP = {
    "check_inventory": "check_inventory",
    "inventory": "check_inventory",
    "check_stock": "check_inventory",
    "fetch_datasheet": "fetch_datasheet",
    "get_datasheet": "fetch_datasheet",
    "download_datasheet": "fetch_datasheet",
    "log_inventory": "log_inventory",
    "add_inventory": "log_inventory",
    "log_part": "log_inventory",
    "generate_bom": "generate_bom",
    "audit_bom": "generate_bom",
    "check_bom": "generate_bom",
}


class TheQuartermaster(BaseAgent):
    """Specialist Agent: Logistics and Documentation.

    Domain: BOM generation/audit, SQLite inventory management, and datasheet retrieval.
    """

    name: str = "TheQuartermaster"
    domain: str = (
        "BOM generation/audit, SQLite inventory management, and datasheet retrieval."
    )
    description: str = (
        "Logistics and documentation agent responsible for bill-of-materials (BOM) generation "
        "and auditing, SQLite inventory tracking, and electronic component datasheet retrieval."
    )

    system_requirements: List[str] = ["sqlite3"]
    consumed_artifacts: List[str] = [
        "part_number",
        "mpn",
        "project_directory",
        "query",
    ]
    produced_artifacts: List[str] = [
        "bom_report",
        "datasheet_path",
        "inventory_status",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "check_inventory": [
            "check_inventory",
            "inventory",
            "check_stock",
        ],
        "fetch_datasheet": [
            "fetch_datasheet",
            "get_datasheet",
            "download_datasheet",
        ],
        "log_inventory": [
            "log_inventory",
            "add_inventory",
            "log_part",
        ],
        "generate_bom": [
            "generate_bom",
            "audit_bom",
            "check_bom",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        datasheet_dir: Optional[Union[str, Path]] = None,
        scout_agent: Optional[Any] = None,
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheQuartermaster agent with inventory database and datasheet storage configuration."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.db_path = (
            Path(db_path).resolve() if db_path else QUARTERMASTER_DB_PATH
        )
        self.datasheet_dir = (
            Path(datasheet_dir).resolve() if datasheet_dir else DATASHEETS_DIR
        )
        self._scout = scout_agent
        logger.info(
            f"[{self.name}] Initialized with DB: {self.db_path}, Datasheets: {self.datasheet_dir}"
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying database path and datasheet directory readiness."""
        base_health = super().health_check()
        try:
            db_exists = self.db_path.exists()
            db_dir_exists = self.db_path.parent.exists()
            datasheet_dir_exists = self.datasheet_dir.exists()
            healthy = (
                db_dir_exists
                and datasheet_dir_exists
                and base_health.get("healthy", True)
            )

            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": (
                    "Operational"
                    if healthy
                    else "Degraded: Required directories inaccessible"
                ),
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {
                    "db_path": str(self.db_path),
                    "db_exists": db_exists,
                    "datasheet_dir": str(self.datasheet_dir),
                    "datasheet_dir_exists": datasheet_dir_exists,
                    **base_health.get("details", {}),
                },
                "dynamic_skills_available": base_health.get(
                    "dynamic_skills_available", []
                ),
                "native_actions_supported": base_health.get(
                    "native_actions_supported", []
                ),
            }
        except Exception as e:
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": False,
                "status": f"Degraded: Exception during health check ({e})",
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {
                    "db_path": str(getattr(self, "db_path", "unknown")),
                    "datasheet_dir": str(
                        getattr(self, "datasheet_dir", "unknown")
                    ),
                },
            }

    def _get_scout(self) -> Any:
        """Lazy-instantiates TheScout if not explicitly provided."""
        if self._scout is None:
            try:
                from charon.agents.scout import TheScout

                self._scout = TheScout()
            except Exception as e:
                logger.warning(
                    f"[{self.name}] Could not initialize TheScout inside Quartermaster: {e}"
                )
        return self._scout

    async def execute(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Quartermaster using DynamicActionPayload schemas."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        clean_prompt = (raw_prompt or "").strip()
        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        # Validate action before Pydantic schema validation so unknown actions raise immediately
        if normalized_action not in VALID_QUARTERMASTER_ACTIONS:
            logger.error(
                f"[{self.name}] Does not recognize the action: {action}"
            )
            raise ValueError(
                f"Unknown action '{action}' for {self.name}"
            )

        if clean_prompt and not any(
            payload_dict.get(k)
            for k in ["query", "part_number", "mpn", "project_directory"]
        ):
            payload_dict["query"] = clean_prompt

        self.report_progress(
            message=f"Executing quartermaster action: '{normalized_action}'",
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
                if normalized_action in VALID_QUARTERMASTER_ACTIONS
                else "check_inventory"
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

        try:
            if target_action == "check_inventory":
                result = check_inventory(
                    self.db_path, self.datasheet_dir, payload, clean_prompt
                )
            elif target_action == "fetch_datasheet":
                result = fetch_datasheet(
                    self.db_path,
                    self.datasheet_dir,
                    self._get_scout(),
                    payload,
                    clean_prompt,
                )
            elif target_action == "log_inventory":
                result = log_inventory(self.db_path, payload, clean_prompt)
            elif target_action == "generate_bom":
                result = generate_bom(self.db_path, payload, clean_prompt)
            else:
                raise ValueError(
                    f"Unknown action '{action}' for {self.name}"
                )

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
            logger.exception(
                f"[{self.name}] Execution error during '{normalized_action}': {e}"
            )
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