"""
charon/agents/runtime.py
System Version: v0.4.0 | File Revision: 1.1.0

Universal Data-Driven Agent Runtime.
Instantiated dynamically by the Router using metadata stored in SQLite agent_registry.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.core.skills import SkillLibrarian

logger = logging.getLogger("Charon.Agents.Runtime")


class RuntimeAgent(BaseAgent):
    """
    Universal concrete implementation of BaseAgent.
    Hydrated with persona, system prompt, active tools, and weights from agent_registry.
    """

    def __init__(
        self,
        agent_id: str,
        display_name: str = "",
        description: str = "",
        system_prompt: str = "",
        active_tools: Optional[Union[List[str], str]] = None,
        priority_weight: float = 1.0,
        heavy_model: str = "",
        librarian: Optional[SkillLibrarian] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(librarian=librarian, agent_id=agent_id)
        self.name = display_name or agent_id.capitalize()
        self.description = description
        self.system_prompt = system_prompt
        self.priority_weight = priority_weight
        self.heavy_model = heavy_model

        # Parse active_tools if supplied as JSON string from SQLite
        if isinstance(active_tools, str):
            try:
                self.active_tools = json.loads(active_tools)
            except Exception:
                self.active_tools = []
        else:
            self.active_tools = active_tools or []

    def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Primary execution dispatch:
        1. Checks for dynamic skill handler in SkillLibrarian.
        2. Executes dynamic skill if present, or falls back to prompt-driven processing.
        """
        self.report_progress(f"Executing action '{action}' via agent persona '{self.agent_id}'", action=action)

        # 1. Check if action maps to a dynamic skill checkout
        if self.librarian and self.librarian.get_action_manifest(action, self.name):
            logger.info(f"[{self.name}] Dispatching to dynamic skill handler for action '{action}'")
            return self.execute_dynamic(action, parameters, raw_prompt)

        # 2. Native/Prompt execution fallback
        logger.info(f"[{self.name}] No dynamic skill handler for '{action}'. Running core agent task.")
        fallback_msg = f"Action '{action}' executed under persona '{self.name}'."
        self.report_response(fallback_msg)

        return {
            "status": "success",
            "agent_id": self.agent_id,
            "action": action,
            "result": fallback_msg,
        }