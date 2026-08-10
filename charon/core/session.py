"""
charon/core/session.py
System Version: v0.3.0 | File Revision: 3.0.1

Module: Core session gateway for Charon.
Manages manifest-driven triage routing, parameter extraction, and agent dispatch.
Acts as a front controller between incoming requests and the lower-level DAG execution coordinator,
handling identity resolution and short-term memory buffering.
"""

import logging
from typing import Any, Dict, List, Optional

import ollama
from pydantic import BaseModel

from charon.core.dispatcher import AgentDispatcher
from charon.core.parser import IntentParser
from charon.core.prompts import get_agent_ack
from charon.core.skills import SkillLibrarian
from charon.intent.manifests import get_agent_manifest
from charon.intent.routing import RoutingPayload
from charon.utils.memory import ConversationBuffer

logger = logging.getLogger("Charon.SessionGateway")


class SessionGateway:
    """The front desk managing session memory, triage parsing, and request pass-through to execution chains."""

    def __init__(
        self,
        heavy_model: str = "llama3.1",
        triage_model: str = "llama3.1",
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.heavy_model = heavy_model
        self.triage_model = triage_model

        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ollama_client = ollama.AsyncClient()
        self.memory = ConversationBuffer(max_turns=5)

        self.parser = IntentParser(
            ollama_client=self.ollama_client,
            triage_model=self.triage_model,
            heavy_model=self.heavy_model,
            memory=self.memory,
            librarian=self.librarian,
        )

        self.dispatcher = AgentDispatcher(
            heavy_model=self.heavy_model,
        )

    def _resolve_agent_id(self, agent_or_role: str) -> str:
        """Resolves a system role name or agent identifier to a dynamic database ID via SkillLibrarian."""
        if hasattr(self.librarian, "resolve_agent_id_for_role"):
            resolved = self.librarian.resolve_agent_id_for_role(agent_or_role)
            if resolved:
                return resolved
        if hasattr(self.librarian, "resolve_agent_id"):
            resolved = self.librarian.resolve_agent_id(agent_or_role)
            if resolved:
                return resolved
        return agent_or_role

    def _get_agent_display_name(self, agent_or_role: str) -> str:
        """Fetches presentation labels via SkillLibrarian accessor functions."""
        resolved_id = self._resolve_agent_id(agent_or_role)
        if hasattr(self.librarian, "get_display_name_for_agent"):
            display_name = self.librarian.get_display_name_for_agent(resolved_id)
            if display_name:
                return display_name
        if hasattr(self.librarian, "get_display_name_for_role"):
            role_label = self.librarian.get_display_name_for_role(agent_or_role)
            if role_label:
                return role_label
        return agent_or_role

    def get_tool_schemas(self, agent: str) -> List[Dict[str, Any]]:
        """Retrieves OpenAI/Ollama tool specifications for the target agent via SkillLibrarian."""
        resolved_agent_id = self._resolve_agent_id(agent)
        if hasattr(self.librarian, "get_agent_tool_schemas"):
            return self.librarian.get_agent_tool_schemas(resolved_agent_id)
        return []

    def record_turn(self, user_input: str, agent_response: str) -> None:
        """Saves a completed interaction turn into short-term conversation history memory."""
        if not agent_response:
            return

        resp_str = str(agent_response).strip()
        intercept_prefixes = (
            "[Awaiting Authorization]",
            "🛡️ GATEKEEPER",
            "[Authorization Denied]",
            "[Task Cancelled]",
        )
        if resp_str.startswith(intercept_prefixes):
            logger.debug("Skipping memory recording for authorization intercept phrase.")
            return

        if hasattr(self.memory, "add_turn") and callable(getattr(self.memory, "add_turn")):
            self.memory.add_turn(user_input, resp_str)
        elif hasattr(self.memory, "append") and callable(getattr(self.memory, "append")):
            self.memory.append({"user": user_input, "assistant": resp_str})
        else:
            logger.warning("ConversationBuffer lacks add_turn/append method. Turn not recorded.")

    async def parse_routing(
        self,
        user_input: str,
        rejected_agents: Optional[List[str]] = None,
    ) -> Optional[RoutingPayload]:
        """Pass 1: Analytical classification determining target agent."""
        return await self.parser.parse_routing(user_input, rejected_agents)

    async def parse_extraction(
        self, user_input: str, agent: str
    ) -> BaseModel:
        """Pass 2: Extract parameters using agent-specific Pydantic intent."""
        resolved_agent_id = self._resolve_agent_id(agent)

        # Context retrieval has been delegated to the lower-level execution coordinator.
        # The parser only receives the raw user input and short-term memory to extract the schema.
        return await self.parser.parse_extraction(user_input, resolved_agent_id)

    async def execute_agent_task(
        self,
        agent: str,
        extraction: Optional[BaseModel],
        user_raw_input: str,
        stream_cb: Any = None,
    ) -> str:
        """Dispatches extracted parameters to specialist agents and records turn context."""
        resolved_agent_id = self._resolve_agent_id(agent)
        display_name = self._get_agent_display_name(resolved_agent_id)

        logger.info(f"Dispatching task to agent: '{display_name}' (ID: {resolved_agent_id})")

        output_text = await self.dispatcher.dispatch(
            agent_id=resolved_agent_id,
            extraction=extraction,
            user_raw_input=user_raw_input,
            stream_cb=stream_cb,
        )

        self.record_turn(user_raw_input, output_text)
        return output_text

    def get_acknowledgment(
        self,
        agent: str,
        action: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> str:
        """Returns a thematic acknowledgment phrase for the routed agent."""
        resolved_agent_id = self._resolve_agent_id(agent)
        return get_agent_ack(
            agent_id=resolved_agent_id,
            action=action or "",
            parameters=parameters,
        )

    def get_agent_manifest_info(self, agent: str):
        """Retrieves the capability manifest for a given agent name or system role."""
        resolved_agent_id = self._resolve_agent_id(agent)
        return get_agent_manifest(resolved_agent_id)