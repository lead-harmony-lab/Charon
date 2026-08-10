"""
charon/agents/engineer/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Specialist Agent: Dynamic Code Generation, Bug Fixing, OS Automation, Sandbox Execution,
and Dynamic Capability Gap Blueprinting. Inherits from BaseAgent. Updated for dynamic intent schemas.
"""

import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import ollama

from charon.agents.base import BaseAgent, CapabilityType, SkillContract
from charon.agents.engineer.generator import handle_generate_script_only
from charon.agents.engineer.runner import (
    handle_execute_sandbox_code,
    handle_run_existing_script,
)
from charon.agents.engineer.solver import handle_solve_edge_case
from charon.config.paths import ensure_ecosystem_directories
from charon.core.contracts import SkillBlueprint
from charon.core.registry import SkillGapRegistry
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.engineer")

VALID_ENGINEER_ACTIONS = (
    "solve_edge_case",
    "generate_script",
    "run_existing_script",
    "execute_sandbox_code",
    "launch_gui_viewer",
    "execute_system_command",
)

ACTION_MAP = {
    "solve_edge_case": "solve_edge_case",
    "solve": "solve_edge_case",
    "run_repair": "solve_edge_case",
    "write_and_execute": "solve_edge_case",
    "solve_coding_task": "solve_edge_case",
    "repair": "solve_edge_case",
    "generate_script": "generate_script",
    "generate_script_only": "generate_script",
    "write_script": "generate_script",
    "draft_script": "generate_script",
    "run_existing_script": "run_existing_script",
    "run_script": "run_existing_script",
    "execute_sandbox_code": "execute_sandbox_code",
    "sandbox_code": "execute_sandbox_code",
    "run_sandbox": "execute_sandbox_code",
    "sandbox": "execute_sandbox_code",
    "launch_gui_viewer": "launch_gui_viewer",
    "open_pdf": "launch_gui_viewer",
    "view_pdf": "launch_gui_viewer",
    "open_file": "launch_gui_viewer",
    "launch_viewer": "launch_gui_viewer",
    "display_pdf": "launch_gui_viewer",
    "show_pdf": "launch_gui_viewer",
    "execute_system_command": "execute_system_command",
    "system_command": "execute_system_command",
    "run_cmd": "execute_system_command",
    "exec_cmd": "execute_system_command",
}


class TheEngineer(BaseAgent):
    """Specialist Agent: The Engineer / Dynamic Bug Fixer, OS Automator, and Fallback Solver.

    Domain: Self-healing Python script generation, iterative bug resolution,
    desktop GUI viewer launching, guarded subshell sandbox execution, and ad-hoc
    capability gap resolution with skill blueprint emission.
    """

    name: str = "TheEngineer"
    domain: str = (
        "Self-healing Python script generation, iterative bug resolution, "
        "desktop GUI viewer launching, guarded subshell sandbox execution, "
        "and dynamic capability gap engineering."
    )
    description: str = (
        "Dynamic code generator, bug fixer, OS automator, sandbox runner, "
        "and capability gap blueprinting specialist."
    )

    system_requirements: List[str] = ["python3"]
    consumed_artifacts: List[str] = ["python_code", "file_path", "system_command", "unsupported_action"]
    produced_artifacts: List[str] = ["execution_result", "generated_script", "skill_blueprint"]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "solve_edge_case": [
            "solve_edge_case",
            "solve",
            "run_repair",
            "write_and_execute",
            "solve_coding_task",
            "repair",
        ],
        "generate_script": [
            "generate_script",
            "generate_script_only",
            "write_script",
            "draft_script",
        ],
        "run_existing_script": [
            "run_existing_script",
            "run_script",
        ],
        "execute_sandbox_code": [
            "execute_sandbox_code",
            "sandbox_code",
            "run_sandbox",
            "sandbox",
        ],
        "launch_gui_viewer": [
            "launch_gui_viewer",
            "open_pdf",
            "view_pdf",
            "open_file",
            "launch_viewer",
            "display_pdf",
            "show_pdf",
        ],
        "execute_system_command": [
            "execute_system_command",
            "system_command",
            "run_cmd",
            "exec_cmd",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        model_name: str = "llama3.1",
        librarian: Optional[SkillLibrarian] = None,
        gap_registry: Optional[SkillGapRegistry] = None,
    ) -> None:
        """Initializes TheEngineer, binding python environment and capability gap registry."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.model_name = model_name
        self.client = ollama.AsyncClient()
        self.python_cmd = sys.executable
        self.gap_registry = gap_registry or SkillGapRegistry.get_instance()
        logger.info(f"[{self.name}] Initialized with Python engine: {self.python_cmd}")

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying Python interpreter accessibility and LLM configuration."""
        base_health = super().health_check()
        try:
            python_exists = Path(self.python_cmd).exists()
            is_healthy = python_exists and base_health.get("healthy", True)

            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": is_healthy,
                "status": "Operational" if is_healthy else f"Degraded: python_exists={python_exists}",
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
                    "python_cmd": self.python_cmd,
                    "model_name": self.model_name,
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
                    "python_cmd": getattr(self, "python_cmd", sys.executable),
                    "model_name": getattr(self, "model_name", "unknown"),
                },
            }

    def _handle_launch_gui_viewer(
        self, payload: DynamicActionPayload, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Launches a desktop GUI application (xdg-open) for a resolved file path."""
        target_path_str = (
            payload.params.get("resolved_file_path") if payload.params else None
        ) or parameters.get("resolved_file_path") or parameters.get("file_path") or parameters.get("path")

        if not target_path_str:
            return {
                "status": "failed",
                "error": "Cannot launch viewer: No 'resolved_file_path' provided in Blackboard or payload.",
            }

        target_path = Path(target_path_str).resolve()
        if not target_path.exists():
            return {
                "status": "failed",
                "error": f"Cannot launch viewer: Target file '{target_path}' does not exist on disk.",
            }

        try:
            proc = subprocess.Popen(
                ["xdg-open", str(target_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info(
                f"[{self.name}] Spawned default GUI viewer for '{target_path}' (PID: {proc.pid})"
            )
            return {
                "status": "success",
                "message": f"Successfully launched default GUI viewer for {target_path.name}.",
                "app_pid": proc.pid,
                "launched_path": str(target_path),
            }
        except Exception as e:
            logger.error(f"[{self.name}] Failed to launch GUI viewer for {target_path}: {e}")
            return {
                "status": "failed",
                "error": f"Failed to spawn GUI viewer: {str(e)}",
            }

    def _handle_execute_system_command(
        self, payload: DynamicActionPayload, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes lightweight system commands synchronously."""
        cmd_str = (
            payload.params.get("command") if payload.params else None
        ) or parameters.get("command") or parameters.get("cmd")

        if not cmd_str:
            return {
                "status": "failed",
                "error": "No 'command' string provided for execution.",
            }

        try:
            res = subprocess.run(
                shlex.split(cmd_str),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "status": "success" if res.returncode == 0 else "failed",
                "returncode": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
            }
        except Exception as e:
            logger.error(f"[{self.name}] System command execution error: {e}")
            return {
                "status": "failed",
                "error": f"Command execution error: {str(e)}",
            }

    def evaluate_capability(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> SkillContract:
        """Evaluates capability for step negotiation.

        The Engineer acts as the universal fallback solver, so if an action is
        neither native nor in SkillLibrarian, The Engineer accepts it as an
        ad-hoc escalation task.
        """
        target = action
        action_clean = str(target or "").lower().strip()
        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        # 1. Native or Dynamic Skill Match (Leverage BaseAgent logic)
        contract = super().evaluate_capability(normalized_action, params)
        if contract.status != "UNSUPPORTED_ACTION":
            return contract

        # 2. Universal Fallback Acceptance
        logger.info(f"[{self.name}] Accepted unrecognized action '{target}' for fallback solving.")
        return SkillContract(
            status="READY",
            capability_type=CapabilityType.NATIVE,
            missing_prerequisites=[],
        )

    async def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Primary routing switch for native actions on The Engineer, validated against DynamicActionPayload."""
        action_clean = str(action or "").lower().strip()

        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            payload_dict = dict(parameters) if parameters else {}
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        payload_dict = dict(parameters) if parameters else {}
        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        if raw_prompt and not any(
            payload_dict.get(k)
            for k in [
                "problem",
                "prompt",
                "task",
                "objective",
                "code",
                "script_path",
                "resolved_file_path",
                "command",
            ]
        ):
            payload_dict["problem"] = raw_prompt.strip()

        self.report_progress(
            message=f"Executing engineer action: '{normalized_action}'",
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
                if normalized_action in VALID_ENGINEER_ACTIONS
                else "solve_edge_case"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        try:
            target_action = payload.call_action or normalized_action

            # Direct OS Handler Routing
            if target_action == "launch_gui_viewer":
                result = self._handle_launch_gui_viewer(payload, parameters)
            elif target_action == "execute_system_command":
                result = self._handle_execute_system_command(payload, parameters)

            # LLM / Sandbox Execution Routing
            elif target_action == "solve_edge_case":
                result = await handle_solve_edge_case(
                    self.client,
                    self.model_name,
                    self.python_cmd,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
                )
            elif target_action == "generate_script":
                result = await handle_generate_script_only(
                    self.client, self.model_name, payload, parameters, raw_prompt
                )
            elif target_action == "run_existing_script":
                result = await handle_run_existing_script(
                    self.python_cmd, payload, parameters, stream_callback
                )
            elif target_action == "execute_sandbox_code":
                result = await handle_execute_sandbox_code(
                    self.python_cmd, payload, parameters, stream_callback
                )
            else:
                logger.warning(
                    f"[{self.name}] Received unknown action '{action}'. Defaulting to ad-hoc self-healing solver."
                )

                # Ad-hoc Fallback Solver
                result = await handle_solve_edge_case(
                    self.client,
                    self.model_name,
                    self.python_cmd,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
                )

                # Draft Blueprint for Capability Gap
                blueprint = SkillBlueprint(
                    suggested_skill_name=f"{action.title().replace('_', '')}Skill",
                    action_name=action,
                    target_agent=parameters.get("target_agent", "The_Quartermaster"),
                    description=f"Auto-generated skill blueprint for handling dynamic action '{action}'.",
                    inputs_required=list(parameters.keys()),
                    outputs_produced=["result_data", "status"],
                    system_dependencies=[],
                    adhoc_code_reference=parameters.get("script_path"),
                )

                # Log gap in threshold registry
                forge_recommendation = self.gap_registry.log_escalation(blueprint)
                if forge_recommendation:
                    logger.warning(
                        f"⚠️ RECURRING GAP THRESHOLD REACHED ({self.gap_registry.get_gap_count(action)}x). "
                        f"SkillBlueprint '{blueprint.suggested_skill_name}' is ready for Charon Forge generation."
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