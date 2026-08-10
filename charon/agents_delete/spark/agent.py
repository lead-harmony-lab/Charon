"""
charon/agents/spark/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Orchestrator class for electrical engineering and firmware tasks.
Inherits from BaseAgent for unified system probing and capability discovery.
Updated for dynamic intent schemas.
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.spark.eda import handle_export_bom, handle_export_gerbers
from charon.agents.spark.firmware import (
    handle_compile_firmware,
    handle_flash_hardware,
)
from charon.agents.spark.utils import find_pcb_file, resolve_project_dir
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.spark")

VALID_SPARK_ACTIONS = (
    "compile_firmware",
    "flash_hardware",
    "export_gerbers",
    "export_bom",
)

ACTION_MAP = {
    "compile_firmware": "compile_firmware",
    "compile": "compile_firmware",
    "build": "compile_firmware",
    "build_firmware": "compile_firmware",
    "flash_hardware": "flash_hardware",
    "flash": "flash_hardware",
    "upload": "flash_hardware",
    "upload_firmware": "flash_hardware",
    "export_gerbers": "export_gerbers",
    "gerbers": "export_gerbers",
    "export_pcb": "export_gerbers",
    "plot_gerbers": "export_gerbers",
    "export_bom": "export_bom",
    "generate_bom": "export_bom",
    "bom": "export_bom",
}


class TheSpark(BaseAgent):
    """Specialist Agent: Electrical and Firmware Domain.

    Domain: EDA automation, firmware compilation, hardware flashing, and Gerber/BOM generation.
    """

    name: str = "TheSpark"
    domain: str = (
        "EDA automation, firmware compilation, hardware flashing, and Gerber/BOM generation."
    )
    description: str = (
        "Electrical engineering and firmware agent responsible for KiCad EDA automation, "
        "PlatformIO firmware compilation, hardware flashing, and Gerber/BOM generation."
    )

    system_requirements: List[str] = ["pio", "kicad-cli"]
    consumed_artifacts: List[str] = [
        "project_directory",
        "pcb_file",
        "firmware_src",
        "board",
    ]
    produced_artifacts: List[str] = [
        "firmware_binary",
        "gerber_files",
        "bom_file",
        "flash_result",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "compile_firmware": [
            "compile_firmware",
            "compile",
            "build",
            "build_firmware",
        ],
        "flash_hardware": [
            "flash_hardware",
            "flash",
            "upload",
            "upload_firmware",
        ],
        "export_gerbers": [
            "export_gerbers",
            "gerbers",
            "export_pcb",
            "plot_gerbers",
        ],
        "export_bom": [
            "export_bom",
            "generate_bom",
            "bom",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        pio_cmd: str = "pio",
        kicad_cli: str = "kicad-cli",
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheSpark agent with PlatformIO and KiCad CLI tool paths."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.pio_cmd = pio_cmd
        self.kicad_cli = kicad_cli
        logger.info(
            f"[{self.name}] Initialized using PlatformIO: {self.pio_cmd} and KiCad CLI: {self.kicad_cli}"
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying CLI tool availability (PlatformIO and KiCad)."""
        base_health = super().health_check()
        try:
            pio_available = (
                shutil.which(self.pio_cmd) is not None
                or Path(self.pio_cmd).exists()
            )
            kicad_available = (
                shutil.which(self.kicad_cli) is not None
                or Path(self.kicad_cli).exists()
            )
            healthy = (pio_available or kicad_available) and base_health.get(
                "healthy", True
            )

            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": (
                    "Operational"
                    if healthy
                    else "Degraded: PlatformIO and KiCad CLI tools not found in PATH"
                ),
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {
                    "pio_cmd": self.pio_cmd,
                    "pio_available": pio_available,
                    "kicad_cli": self.kicad_cli,
                    "kicad_available": kicad_available,
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
                    "pio_cmd": str(getattr(self, "pio_cmd", "pio")),
                    "kicad_cli": str(getattr(self, "kicad_cli", "kicad-cli")),
                },
            }

    async def execute(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Spark's capabilities using DynamicActionPayload schemas."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        if normalized_action not in VALID_SPARK_ACTIONS:
            logger.error(
                f"[{self.name}] Does not recognize action: {normalized_action}"
            )
            raise ValueError(
                f"Unknown action '{normalized_action}' for {self.name}"
            )

        self.report_progress(
            message=f"Executing spark action: '{normalized_action}'",
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
                if normalized_action in VALID_SPARK_ACTIONS
                else "compile_firmware"
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
            if target_action == "compile_firmware":
                result = self._compile_firmware(payload, raw_params, raw_prompt)

            elif target_action == "flash_hardware":
                result = self._flash_hardware(payload, raw_params, raw_prompt)

            elif target_action == "export_gerbers":
                result = self._export_gerbers(payload, raw_params, raw_prompt)

            elif target_action == "export_bom":
                result = self._export_bom(payload, raw_params, raw_prompt)

            else:
                raise ValueError(
                    f"Unknown action '{normalized_action}' for {self.name}"
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

    # =========================================================================
    # BACKWARD COMPATIBILITY HELPERS & DELEGATES
    # =========================================================================

    def _resolve_project_dir(
        self,
        params: Dict[str, Any],
        raw_prompt: str = "",
        payload: Optional[Any] = None,
    ) -> Optional[Path]:
        return resolve_project_dir(params, raw_prompt, payload=payload)

    def _find_pcb_file(
        self,
        params: Dict[str, Any],
        raw_prompt: str = "",
        payload: Optional[Any] = None,
    ) -> Optional[Path]:
        return find_pcb_file(params, raw_prompt, payload=payload)

    def _compile_firmware(
        self,
        payload: Optional[Any],
        params: Dict[str, Any],
        raw_prompt: str = "",
    ) -> str:
        return handle_compile_firmware(
            self.pio_cmd, payload, params, raw_prompt=raw_prompt
        )

    def _flash_hardware(
        self,
        payload: Optional[Any],
        params: Dict[str, Any],
        raw_prompt: str = "",
    ) -> str:
        return handle_flash_hardware(
            self.pio_cmd, payload, params, raw_prompt=raw_prompt
        )

    def _export_gerbers(
        self,
        payload: Optional[Any],
        params: Dict[str, Any],
        raw_prompt: str = "",
    ) -> str:
        return handle_export_gerbers(
            self.kicad_cli, payload, params, raw_prompt=raw_prompt
        )

    def _export_bom(
        self,
        payload: Optional[Any],
        params: Dict[str, Any],
        raw_prompt: str = "",
    ) -> str:
        return handle_export_bom(
            self.kicad_cli, payload, params, raw_prompt=raw_prompt
        )