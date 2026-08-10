"""
charon/agents/generalist/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Specialist Agent Class: The Concierge & System Utility Handler for Charon.
Inherits from BaseAgent for unified system probing and capability discovery. Updated for dynamic intent schemas.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union

import ollama

from charon.agents.base import BaseAgent
from charon.agents.generalist.handlers import (
    handle_answer_query,
    handle_calculate_math,
    handle_execute_system_task,
    handle_get_system_info,
    handle_synthesize_rag,
)
from charon.agents.generalist.prompts import (
    ACTION_MAP,
    SYSTEM_ACTION_PATTERNS,
    VALID_GENERALIST_ACTIONS,
)
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.generalist")


class TheGeneralist(BaseAgent):
    """Specialist Agent: The Concierge & System Utility Handler.

    Domain: General knowledge retrieval, system state diagnostics, basic OS execution,
    deterministic/assisted computation, and RAG technical context synthesis.
    """

    name: str = "TheGeneralist"
    domain: str = (
        "General knowledge retrieval, system state diagnostics, basic OS execution, "
        "deterministic/assisted computation, and RAG technical context synthesis."
    )
    description: str = (
        "Concierge and system utility agent for general knowledge, system diagnostics, "
        "deterministic math computation, OS command execution, and RAG synthesis."
    )

    system_requirements: List[str] = []
    consumed_artifacts: List[str] = ["prompt", "context", "expression", "system_command"]
    produced_artifacts: List[str] = ["text_response", "calculation_result", "system_info", "rag_synthesis"]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "answer_query": [
            "answer_query",
            "ask",
            "query",
            "chat",
            "general_query",
            "conversation",
            "explain",
        ],
        "synthesize_rag": [
            "synthesize_rag",
            "rag",
            "synthesize",
            "combine_knowledge",
        ],
        "calculate_math": [
            "calculate_math",
            "math",
            "calculate",
            "compute",
            "calculator",
        ],
        "system_info": [
            "system_info",
            "sys_info",
            "specs",
            "host_info",
        ],
        "execute_system_command": [
            "execute_system_command",
            "system_task",
            "system_command",
            "cmd",
            "shell",
            "exec",
        ],
        "acknowledge": [
            "acknowledge",
            "ack",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(
        self,
        model_name: str = "llama3.1",
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheGeneralist concierge agent and binds the LLM client."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.model_name = model_name
        self.client = ollama.AsyncClient()
        logger.info(f"[{self.name}] Initialized with model: {self.model_name}")

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying model configuration and client readiness."""
        base_health = super().health_check()
        try:
            healthy = bool(self.model_name) and base_health.get("healthy", True)
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": "Operational" if healthy else "Degraded: Missing model configuration",
                "missing_dependencies": base_health.get("missing_dependencies", []),
                "details": {
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
                    "model_name": getattr(self, "model_name", "unknown"),
                },
            }

    async def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Generalist's capabilities, validated against DynamicActionPayload."""
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
            for k in ["prompt", "query", "command", "expression", "context"]
        ):
            payload_dict["prompt"] = raw_prompt.strip()

        self.report_progress(
            message=f"Executing generalist action: '{normalized_action}'",
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
                if normalized_action in VALID_GENERALIST_ACTIONS
                else "answer_query"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        target_action = payload.call_action or normalized_action
        payload_params = payload.params if payload.params else {}

        prompt_text = str(
            payload_params.get("prompt")
            or payload_params.get("query")
            or payload_params.get("command")
            or payload_dict.get("command")
            or raw_prompt
            or ""
        ).lower()

        try:
            # Deterministic Guard: Intercept conversational extraction if prompt targets system hardware
            if target_action == "answer_query":
                if any(re.search(pat, prompt_text) for pat in SYSTEM_ACTION_PATTERNS):
                    logger.info(
                        f"[{self.name}] Deterministic Guard: Redirecting query to execute_system_command based on OS keywords."
                    )
                    result = await handle_execute_system_task(
                        self.client,
                        self.model_name,
                        payload,
                        parameters,
                        raw_prompt,
                        stream_callback,
                    )
                else:
                    result = await handle_answer_query(
                        self.client,
                        self.model_name,
                        payload,
                        parameters,
                        raw_prompt,
                        stream_callback,
                    )

            elif target_action == "synthesize_rag":
                result = await handle_synthesize_rag(
                    self.client,
                    self.model_name,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
                )

            elif target_action == "calculate_math":
                result = await handle_calculate_math(
                    self.client,
                    self.model_name,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
                )

            elif target_action == "system_info":
                result = await handle_get_system_info()

            elif target_action in ("execute_system_command", "system_task"):
                result = await handle_execute_system_task(
                    self.client,
                    self.model_name,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
                )

            elif target_action == "acknowledge":
                result = "Your directive has been noted. I shall see to the arrangements."

            else:
                logger.warning(
                    f"[{self.name}] Received unknown action '{action}'. Defaulting to general query processing."
                )
                result = await handle_answer_query(
                    self.client,
                    self.model_name,
                    payload,
                    parameters,
                    raw_prompt,
                    stream_callback,
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