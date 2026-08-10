"""
charon/agents/planner/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Primary entry point for The Planner.
Inherits from BaseAgent for unified system probing and capability discovery.
Updated for dynamic intent schemas.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import ollama

from charon.agents.base import BaseAgent
from charon.agents.planner.constants import ACTION_MAP, VALID_PLANNER_ACTIONS
from charon.agents.planner.dag import decompose_task
from charon.agents.planner.diagnostics import analyze_error_logs
from charon.agents.planner.sandbox import execute_sandbox_code
from charon.agents.planner.sequencing import draft_build_sequence
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.planner")


class ThePlanner(BaseAgent):
    """Specialist Agent: The Strategist & Metacognitive Supervisor.

    Domain: Dynamic code generation, sandbox execution, path resolution,
    multi-step reasoning, and multi-agent plan decomposition.
    """

    name: str = "ThePlanner"
    domain: str = (
        "Dynamic code generation, sandbox execution, path resolution, "
        "multi-step reasoning, and multi-agent plan decomposition."
    )
    description: str = (
        "Strategist and metacognitive supervisor responsible for multi-agent task breakdown "
        "(DAG generation), build sequence drafting, error log diagnostics, and sandbox code execution."
    )

    system_requirements: List[str] = ["ollama", "python"]
    consumed_artifacts: List[str] = ["task_description", "code", "logs", "context"]
    produced_artifacts: List[str] = [
        "plan_dag",
        "execution_result",
        "diagnostics_report",
        "build_sequence",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "decompose_task": [
            "decompose_task",
            "decompose",
            "plan",
            "dag",
            "task_breakdown",
        ],
        "draft_build_sequence": [
            "draft_build_sequence",
            "draft_sequence",
            "build_sequence",
            "sequence",
        ],
        "analyze_error_logs": [
            "analyze_error_logs",
            "analyze_logs",
            "diagnose",
            "debug_logs",
        ],
        "execute_sandbox_code": [
            "execute_sandbox_code",
            "sandbox",
            "run_sandbox",
            "execute_sandbox",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        model_name: str = "llama3.1",
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes ThePlanner agent, binding Ollama client and Python execution engine."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.model_name = model_name
        self.client = ollama.AsyncClient()
        self.python_cmd = sys.executable
        logger.info(
            f"[{self.name}] Initialized using Python engine: {self.python_cmd} and Model: {self.model_name}"
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying Python execution environment and model configuration."""
        base_health = super().health_check()
        try:
            python_exists = Path(self.python_cmd).exists()
            healthy = python_exists and base_health.get("healthy", True)
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": "Operational" if healthy else "Degraded: Python executable missing",
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

    async def execute(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[str, List[Dict[str, Any]], Dict[str, Any]]:
        """The primary routing switch for The Planner's capabilities using DynamicActionPayload."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        self.report_progress(
            message=f"Executing planner action: '{normalized_action}'",
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
                if normalized_action in VALID_PLANNER_ACTIONS
                else "decompose_task"
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
            if target_action == "decompose_task":
                result = await decompose_task(
                    client=self.client,
                    model_name=self.model_name,
                    params=raw_params,
                    raw_prompt=raw_prompt,
                    payload=payload,
                )

            elif target_action == "draft_build_sequence":
                result = await draft_build_sequence(
                    client=self.client,
                    model_name=self.model_name,
                    params=raw_params,
                    raw_prompt=raw_prompt,
                    stream_callback=stream_callback,
                    payload=payload,
                )

            elif target_action == "analyze_error_logs":
                result = await analyze_error_logs(
                    client=self.client,
                    model_name=self.model_name,
                    params=raw_params,
                    raw_prompt=raw_prompt,
                    stream_callback=stream_callback,
                    payload=payload,
                )

            elif target_action == "execute_sandbox_code":
                result = await execute_sandbox_code(
                    client=self.client,
                    model_name=self.model_name,
                    python_cmd=self.python_cmd,
                    params=raw_params,
                    raw_prompt=raw_prompt,
                    stream_callback=stream_callback,
                    payload=payload,
                )

            else:
                raise ValueError(f"Unknown Planner action: '{target_action}'")

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