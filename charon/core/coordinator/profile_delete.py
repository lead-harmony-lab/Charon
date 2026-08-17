"""
charon/core/coordinator/profile.py
System Version: v0.9.0 | File Revision: 9.0.0

Module: Work Contract Agent Profile and Envelope Capability Mapping.
Re-orients AgentProfile and CapabilityContract around Work Contracts (Default Actions)
and Pydantic Artifact Schemas rather than micro-tool action lists.
Enforces strict DB resolution via SkillLibrarian SSOT without synthetic fallbacks.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from charon.core.coordinator.blackboard import EscalationLevel
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("charon.core.coordinator.profile")


class RoleConfigurationError(RuntimeError):
    """Raised when an agent, role, or Work Contract cannot be resolved in SkillLibrarian SSOT."""


def _resolve_agent_id(agent_or_role: Any, librarian: Optional[SkillLibrarian] = None) -> str:
    """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT.

    Fails fast with RoleConfigurationError if unresolvable.
    """
    if not agent_or_role:
        raise RoleConfigurationError("[Profile Fault] Empty agent or role provided for resolution.")

    role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
    if not role_str:
        raise RoleConfigurationError("[Profile Fault] Invalid empty string role representation.")

    lib = librarian or SkillLibrarian.get_instance()

    if hasattr(lib, "resolve_agent_id_for_role") and callable(lib.resolve_agent_id_for_role):
        resolved = lib.resolve_agent_id_for_role(role_str)
        if resolved:
            return str(resolved).strip()

    if hasattr(lib, "resolve_agent_id") and callable(lib.resolve_agent_id):
        resolved = lib.resolve_agent_id(role_str)
        if resolved:
            return str(resolved).strip()

    # Strict SSOT: Synthetic string fallbacks prohibited
    raise RoleConfigurationError(
        f"[Profile Fault] Role/Agent '{role_str}' could not be resolved to an active agent in SkillLibrarian SSOT."
    )


def get_default_escalation_level() -> EscalationLevel:
    """Safely retrieves default escalation level attribute from EscalationLevel enum."""
    return getattr(EscalationLevel, "L1_SPECIALIST", list(EscalationLevel)[0])


class CapabilityContract(BaseModel):
    """Contract definition representing an Agent's Work Contract envelope capability."""

    capability_name: str  # Default Action / Work Contract Identifier
    agent: str
    description: str = ""
    artifact_schema: str = ""  # Strictly typed expected Pydantic artifact schema
    consumed_artifacts: List[str] = Field(default_factory=list)
    produced_artifacts: List[str] = Field(default_factory=list)
    escalation_level: Any = Field(default_factory=get_default_escalation_level)
    required_binaries: List[str] = Field(default_factory=list)

    @property
    def role(self) -> str:
        """Alias property for agent identification for role-based system callers."""
        return self.agent


class AgentProfile:
    """Represents an agent's registered Work Contract envelope and hardware readiness metadata."""

    def __init__(
        self,
        agent: Union[str, Any],
        name: str = "",
        manifest: Any = None,
        work_contract: Optional[CapabilityContract] = None,
        verified_binaries: Optional[Set[str]] = None,
        missing_binaries: Optional[Set[str]] = None,
        is_healthy: bool = True,
        health_status: Optional[Dict[str, Any]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.agent = agent
        self._agent_id = _resolve_agent_id(agent, self.librarian)

        display_name = name
        if not display_name:
            if hasattr(self.librarian, "get_display_name_for_agent") and callable(
                self.librarian.get_display_name_for_agent
            ):
                display_name = self.librarian.get_display_name_for_agent(self._agent_id)
            elif hasattr(self.librarian, "get_display_name_for_role") and callable(
                self.librarian.get_display_name_for_role
            ):
                display_name = self.librarian.get_display_name_for_role(self._agent_id)

        self.name = display_name or self._agent_id
        self.manifest = manifest
        self._work_contract = work_contract
        self.verified_binaries = verified_binaries or set()
        self.missing_binaries = missing_binaries or set()
        self.is_healthy = is_healthy
        self.health_status = health_status or {"healthy": True, "status": "Operational"}

    @property
    def agent_id(self) -> str:
        """Returns the canonical string representation of the agent ID resolved from DB."""
        return self._agent_id

    @property
    def role_id(self) -> str:
        """Alias property for agent_id to support role abstraction."""
        return self.agent_id

    @property
    def role(self) -> Any:
        """Alias property for agent object to support role abstraction."""
        return self.agent

    def _build_work_contract(self, default_action_name: str, details: Dict[str, Any]) -> CapabilityContract:
        """Constructs a CapabilityContract envelope from librarian Default Action details."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            raise RoleConfigurationError(
                f"[Profile Fault] Work Contract '{default_action_name}' for agent '{self.agent_id}' is INACTIVE."
            )

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []

        return CapabilityContract(
            capability_name=details.get("capability_name", details.get("action_name", default_action_name)),
            agent=self.agent_id,
            description=details.get("description", ""),
            artifact_schema=details.get("artifact_schema", details.get("output_schema", "")),
            consumed_artifacts=details.get("consumed_artifacts", []),
            produced_artifacts=details.get("produced_artifacts", []),
            escalation_level=details.get("escalation_level", get_default_escalation_level()),
            required_binaries=req_binaries,
        )

    @property
    def work_contract(self) -> CapabilityContract:
        """Resolves and returns the primary Work Contract envelope for this agent from SkillLibrarian SSOT."""
        if self._work_contract is None:
            default_action = None
            if hasattr(self.librarian, "get_default_action_for_agent") and callable(
                self.librarian.get_default_action_for_agent
            ):
                default_action = self.librarian.get_default_action_for_agent(self.agent_id)
            elif hasattr(self.librarian, "get_default_action_for_role") and callable(
                self.librarian.get_default_action_for_role
            ):
                default_action = self.librarian.get_default_action_for_role(self.agent_id)

            if not default_action:
                raise RoleConfigurationError(
                    f"[Profile Fault] No active Default Action / Work Contract found for agent '{self.agent_id}' in SkillLibrarian."
                )

            details = self.librarian.get_action_details(default_action)
            if not details:
                raise RoleConfigurationError(
                    f"[Profile Fault] Failed to load action details for Work Contract '{default_action}'."
                )

            self._work_contract = self._build_work_contract(default_action, details)

        return self._work_contract

    @property
    def capabilities(self) -> Dict[str, CapabilityContract]:
        """Returns map of registered capabilities, anchored to the agent's singular Work Contract."""
        contract = self.work_contract
        return {contract.capability_name: contract}

    def get_capability(self, capability_name: str) -> Optional[CapabilityContract]:
        """Finds a capability contract by name if it matches the agent's Work Contract envelope."""
        contract = self.work_contract
        if contract.capability_name == capability_name or capability_name == "default_action":
            return contract
        return None

    def is_equipped(
        self, capability_name: str, available_artifacts: List[str]
    ) -> Tuple[bool, List[str]]:
        """Checks if the profile's Work Contract prerequisites (artifacts and binaries) are satisfied."""
        cap = self.get_capability(capability_name)
        if not cap:
            return False, [
                f"Capability '{capability_name}' does not match agent Work Contract ('{self.work_contract.capability_name}')"
            ]

        missing_reqs = []
        for artifact in cap.consumed_artifacts:
            if artifact not in available_artifacts:
                missing_reqs.append(f"Missing artifact: {artifact}")

        for binary in cap.required_binaries:
            if binary in self.missing_binaries:
                missing_reqs.append(f"Missing system binary: {binary}")

        return len(missing_reqs) == 0, missing_reqs