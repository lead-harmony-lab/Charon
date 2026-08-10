"""
charon/core/coordinator/profile.py
System Version: v0.4.1 | File Revision: 1.3.0

Module: Agent profile definition and capability mapping.
Defines CapabilityContract and AgentProfile integrated with dynamic SkillLibrarian.
Enforces active skill status checks and strict schema alignment.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from charon.core.coordinator.blackboard import EscalationLevel
from charon.core.skills import SkillLibrarian

logger = logging.getLogger("charon.core.coordinator.profile")


def get_default_escalation_level() -> EscalationLevel:
    """Safely retrieves default escalation level attribute from EscalationLevel enum."""
    return getattr(EscalationLevel, "L1_SPECIALIST", list(EscalationLevel)[0])


class CapabilityContract(BaseModel):
    """Contract definition for an agent/role capability / action."""

    capability_name: str
    agent: str
    description: str = ""
    consumed_artifacts: List[str] = Field(default_factory=list)
    produced_artifacts: List[str] = Field(default_factory=list)
    escalation_level: Any = Field(default_factory=get_default_escalation_level)
    required_binaries: List[str] = Field(default_factory=list)

    @property
    def role(self) -> str:
        """Alias property for agent identification for role-based system callers."""
        return self.agent


class AgentProfile:
    """Represents an agent's registered capabilities and operational metadata."""

    def __init__(
        self,
        agent: Union[str, Any],
        name: str = "",
        manifest: Any = None,
        capabilities: Optional[Dict[str, CapabilityContract]] = None,
        verified_binaries: Optional[Set[str]] = None,
        missing_binaries: Optional[Set[str]] = None,
        is_healthy: bool = True,
        health_status: Optional[Dict[str, Any]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.agent = agent
        agent_str = agent.value if hasattr(agent, "value") else str(agent)
        self.librarian = librarian or SkillLibrarian.get_instance()

        # Resolve display label dynamically via SkillLibrarian accessor or fallback
        display_name = name
        if not display_name:
            if hasattr(self.librarian, "get_display_name_for_agent"):
                display_name = self.librarian.get_display_name_for_agent(agent_str)
            elif hasattr(self.librarian, "get_display_name_for_role"):
                display_name = self.librarian.get_display_name_for_role(agent_str)

        self.name = display_name or agent_str
        self.manifest = manifest
        self._capabilities = capabilities or {}
        self.verified_binaries = verified_binaries or set()
        self.missing_binaries = missing_binaries or set()
        self.is_healthy = is_healthy
        self.health_status = health_status or {"healthy": True, "status": "Operational"}

    @property
    def agent_id(self) -> str:
        """Returns the normalized string representation of the agent ID."""
        return self.agent.value if hasattr(self.agent, "value") else str(self.agent)

    @property
    def role_id(self) -> str:
        """Alias property for agent_id to support role abstraction."""
        return self.agent_id

    @property
    def role(self) -> Any:
        """Alias property for agent object to support role abstraction."""
        return self.agent

    def _build_contract(self, name: str, details: Dict[str, Any]) -> Optional[CapabilityContract]:
        """Constructs a CapabilityContract instance from librarian action details if ACTIVE."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            logger.debug(f"[Profile] Skipping inactive capability '{name}' (status: {details.get('status')})")
            return None

        target_agent = (
            details.get("agent")
            or details.get("role")
            or details.get("primary_agent_id")
            or details.get("primary_role_id")
            or self.agent_id
        )
        target_agent_str = target_agent.value if hasattr(target_agent, "value") else str(target_agent)

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []

        return CapabilityContract(
            capability_name=details.get(
                "capability_name", details.get("action_name", name)
            ),
            agent=target_agent_str,
            description=details.get("description", ""),
            consumed_artifacts=details.get("consumed_artifacts", []),
            produced_artifacts=details.get("produced_artifacts", []),
            escalation_level=details.get(
                "escalation_level", get_default_escalation_level()
            ),
            required_binaries=req_binaries,
        )

    @property
    def capabilities(self) -> Dict[str, CapabilityContract]:
        """Returns registered capabilities dict, lazily populated via SkillLibrarian if empty."""
        if not self._capabilities and hasattr(self.librarian, "list_available_actions"):
            action_names = self.librarian.list_available_actions(self.agent_id) or []
            for name in action_names:
                details = self.librarian.get_action_details(name)
                if details:
                    contract = self._build_contract(name, details)
                    if contract:
                        self._capabilities[name] = contract
        return self._capabilities

    def get_capability(self, capability_name: str) -> Optional[CapabilityContract]:
        """Finds a specific capability contract by name."""
        if capability_name in self.capabilities:
            return self.capabilities[capability_name]

        details = self.librarian.get_action_details(capability_name)
        if details:
            contract = self._build_contract(capability_name, details)
            if contract:
                self._capabilities[capability_name] = contract
                return contract
        return None

    def is_equipped(
        self, capability_name: str, available_artifacts: List[str]
    ) -> Tuple[bool, List[str]]:
        """Checks if the profile has required binaries and artifacts available."""
        cap = self.get_capability(capability_name)
        if not cap:
            return False, [f"Missing capability contract: {capability_name}"]

        missing_reqs = []
        for artifact in cap.consumed_artifacts:
            if artifact not in available_artifacts:
                missing_reqs.append(f"Missing artifact: {artifact}")

        for binary in cap.required_binaries:
            if binary in self.missing_binaries:
                missing_reqs.append(f"Missing system binary: {binary}")

        return len(missing_reqs) == 0, missing_reqs