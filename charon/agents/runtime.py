"""
charon/agents/runtime.py
System Version: v0.4.0 | File Revision: 1.2.0

Universal Data-Driven Agent Runtime.
Instantiated dynamically by the Router using metadata stored in SQLite agent_registry.
Enforces strict DB SSOT skill resolution and fail-fast execution with zero mock fallbacks.
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
    Executes skills mapped to agent_id in DB SSOT and fails fast on unregistered actions.
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
        1. Queries SkillLibrarian SSOT for dynamic skill registered to this agent_id.
        2. Executes registered skill handler.
        3. FAILS FAST if action is not registered in the database for this agent persona.
        """
        self.report_progress(f"Executing action '{action}' via agent persona '{self.agent_id}'", action=action)

        if not self.librarian:
            raise RuntimeError(f"[FAIL-FAST] SkillLibrarian unavailable for runtime agent '{self.agent_id}'.")

        # 1. Resolve registered skill handler via Librarian SSOT
        has_action = False
        if hasattr(self.librarian, "get_action_manifest"):
            has_action = bool(self.librarian.get_action_manifest(action, self.agent_id))
        elif hasattr(self.librarian, "list_available_actions"):
            has_action = action in self.librarian.list_available_actions(self.agent_id)

        if has_action:
            logger.info(f"[{self.name}] Dispatching to dynamic skill handler for action '{action}'")
            return self.execute_dynamic(action, parameters, raw_prompt)

        # 2. FAIL FAST: Reject unregistered skill execution immediately
        raise ValueError(
            f"[FAIL-FAST] Unregistered action '{action}' requested for agent '{self.agent_id}' ({self.name}). "
            f"Action must be registered in the database 'skills' table bound to this agent_id."
        )