"""
charon/agents/machinist/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Specialist Agent: The Fabrication Bridge.

Manages CAD automation, CAM slicing, toolpath processing, and 3D printer/CNC hardware transmission.
Inherits from BaseAgent for standardized system probing and capability discovery. Updated for dynamic intent schemas.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.machinist.cad import export_cad_to_stl, inspect_cad_files
from charon.agents.machinist.printer import transmit_to_printer
from charon.agents.machinist.slicing import detect_slicer, generate_gcode
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.machinist")

VALID_MACHINIST_ACTIONS = (
    "export_cad_to_stl",
    "generate_gcode",
    "transmit_to_printer",
    "inspect_cad_files",
)

ACTION_MAP = {
    "export_cad_to_stl": "export_cad_to_stl",
    "export_stl": "export_cad_to_stl",
    "stl": "export_cad_to_stl",
    "convert_cad": "export_cad_to_stl",
    "generate_gcode": "generate_gcode",
    "slice": "generate_gcode",
    "slicing": "generate_gcode",
    "gcode": "generate_gcode",
    "transmit_to_printer": "transmit_to_printer",
    "transmit": "transmit_to_printer",
    "print": "transmit_to_printer",
    "upload_gcode": "transmit_to_printer",
    "send_to_printer": "transmit_to_printer",
    "inspect_cad_files": "inspect_cad_files",
    "list_cad": "inspect_cad_files",
    "cad_info": "inspect_cad_files",
    "scan_cad": "inspect_cad_files",
}


class TheMachinist(BaseAgent):
    """Specialist Agent: The Fabrication Bridge.

    Domain: CAD automation, CAM slicing, toolpath processing, and 3D printer/CNC hardware transmission.
    """

    name: str = "TheMachinist"
    domain: str = (
        "CAD automation, CAM slicing, toolpath processing, and 3D printer/CNC hardware transmission."
    )
    description: str = (
        "Fabrication bridge specialist for CAD-to-STL conversion, CAM slicing (G-code generation), "
        "3D printer/CNC transmission, and CAD workspace inspection."
    )

    system_requirements: List[str] = ["prusa-slicer"]
    consumed_artifacts: List[str] = ["cad_file", "stl_file", "gcode_file", "project_name"]
    produced_artifacts: List[str] = ["stl_file", "gcode_file", "transmission_status", "cad_inspection"]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "export_cad_to_stl": [
            "export_cad_to_stl",
            "export_stl",
            "stl",
            "convert_cad",
        ],
        "generate_gcode": [
            "generate_gcode",
            "slice",
            "slicing",
            "gcode",
        ],
        "transmit_to_printer": [
            "transmit_to_printer",
            "transmit",
            "print",
            "upload_gcode",
            "send_to_printer",
        ],
        "inspect_cad_files": [
            "inspect_cad_files",
            "list_cad",
            "cad_info",
            "scan_cad",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        slicer_cmd: Optional[str] = None,
        printer_url: Optional[str] = None,
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheMachinist agent, binds slicer CLI and hardware endpoints."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.slicer_cmd = slicer_cmd or detect_slicer()
        self.printer_url = printer_url or os.getenv(
            "PRINTER_URL", "http://192.168.1.100"
        )
        logger.info(
            f"[{self.name}] Initialized. Active Slicer: {self.slicer_cmd or 'None detected'}"
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying slicer toolchain availability and printer endpoint configuration."""
        base_health = super().health_check()
        try:
            slicer_available = bool(self.slicer_cmd)
            printer_configured = bool(self.printer_url)
            healthy = slicer_available and base_health.get("healthy", True)

            status_msg = (
                "Operational"
                if healthy
                else "Degraded: No active CAM slicer binary detected"
            )
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": status_msg,
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
                    "slicer_cmd": self.slicer_cmd or "Not detected",
                    "printer_url": self.printer_url,
                    "printer_configured": printer_configured,
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
                    "slicer_cmd": getattr(self, "slicer_cmd", None),
                    "printer_url": getattr(self, "printer_url", None),
                },
            }

    def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Machinist's capabilities, validated against DynamicActionPayload."""
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            payload_dict = dict(parameters) if parameters else {}
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        payload_dict = dict(parameters) if parameters else {}
        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        if raw_prompt and not any(
            payload_dict.get(k)
            for k in [
                "source_file",
                "cad_file",
                "stl_file",
                "gcode_file",
                "project_name",
                "file",
            ]
        ):
            payload_dict["source_file"] = raw_prompt.strip()

        self.report_progress(
            message=f"Executing machinist action: '{normalized_action}'",
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
                if normalized_action in VALID_MACHINIST_ACTIONS
                else "inspect_cad_files"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        target_action = payload.call_action or normalized_action

        try:
            if target_action == "export_cad_to_stl":
                result = export_cad_to_stl(payload, parameters, raw_prompt)

            elif target_action == "generate_gcode":
                result = generate_gcode(self.slicer_cmd, payload, parameters, raw_prompt)

            elif target_action == "transmit_to_printer":
                result = transmit_to_printer(self.printer_url, payload, parameters, raw_prompt)

            elif target_action == "inspect_cad_files":
                result = inspect_cad_files(payload, parameters, raw_prompt)

            else:
                logger.error(
                    f"[{self.name}] Does not recognize action: {target_action}"
                )
                raise ValueError(
                    f"Unknown action '{target_action}' for {self.name}"
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