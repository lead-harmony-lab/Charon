"""
charon/core/coordinator/discovery.py
System Version: v0.4.1 | File Revision: 2.4.0

Module: Coordinator Agent & Role Discovery & Probing Manager.
Handles agent and role registration, candidate preplanning, live capability probing,
host binary availability verification, dynamic profile building, and
gap detection with hard fail-fast assertions if system roles or contracts are missing.
"""

import logging
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from charon.agents.base import BaseAgent
from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    UnfulfilledRequirement,
)
from charon.core.coordinator.profile import (
    AgentProfile,
    CapabilityContract,
    get_default_escalation_level,
)
from charon.core.skills.librarian import SkillLibrarian

# Safe import for legacy manifest lookup
try:
    from charon.intent.manifests import get_agent_manifest
except ImportError:
    get_agent_manifest = lambda agent_id: None

logger = logging.getLogger("Charon.Discovery")

FALLBACK_ENGINEER_ROLE = "system_engineer"


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role, default agent, or action contract is not assigned in runtime or DB state."""


class AgentDiscoveryManager:
    """Manages agent/role registration, health probing, dynamic profile resolution, and gap escalation."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.agents: Dict[str, BaseAgent] = {}
        self.active_profiles: Dict[str, AgentProfile] = {}

    def register_agent(self, agent_key: Any, agent_instance: BaseAgent) -> None:
        """Registers a live BaseAgent instance with the Coordinator discovery pool for health probing."""
        agent_str = str(getattr(agent_key, "value", agent_key)).lower()
        self.agents[agent_str] = agent_instance
        logger.info(
            f"[Discovery] Registered live agent instance for '{agent_str}' ({agent_instance.name})"
        )

    def probe_agent(self, agent: Any, probe_type: str = "full") -> Dict[str, Any]:
        """Probes a specific registered agent instance for runtime health and dynamic capabilities."""
        agent_str = str(getattr(agent, "value", agent)).lower()
        agent_instance = self.agents.get(agent_str)

        if agent_instance and hasattr(agent_instance, "probe"):
            return agent_instance.probe(probe_type=probe_type)

        return {
            "healthy": False,
            "status": f"Agent instance for '{agent_str}' not registered in runtime pool.",
            "details": {},
        }

    def probe_all_agents(self, probe_type: str = "full") -> Dict[str, Dict[str, Any]]:
        """Probes all registered live agent instances."""
        return {
            agent_str: instance.probe(probe_type=probe_type)
            for agent_str, instance in self.agents.items()
            if hasattr(instance, "probe")
        }

    def preplan_and_build_profiles(
        self, prompt: str, metadata: Dict[str, Any]
    ) -> Dict[str, AgentProfile]:
        """Identifies target candidate agents and constructs dynamic AgentProfiles from the DB."""
        candidates = self._preplan_candidate_agents(prompt, metadata)
        self.active_profiles = self._build_agent_profiles(candidates)
        return self.active_profiles

    def _ensure_profile_active(self, agent: Any) -> Optional[AgentProfile]:
        """Ensures an AgentProfile exists in self.active_profiles, constructing it on-demand if missing."""
        agent_str = str(getattr(agent, "value", agent)).lower()
        if agent_str in self.active_profiles:
            return self.active_profiles[agent_str]

        logger.info(
            f"[Discovery] Performing on-demand hydration for unplanned agent/role '{agent_str}'."
        )
        built = self._build_agent_profiles([agent_str])
        if agent_str in built:
            self.active_profiles[agent_str] = built[agent_str]
            return self.active_profiles[agent_str]

        return None

    def _preplan_candidate_agents(
        self, prompt: str, metadata: Dict[str, Any]
    ) -> List[str]:
        """Dynamically queries SkillLibrarian for matching agents based on intent metadata."""
        candidates: Set[str] = set()

        # 1. Extract from metadata routing hints
        for source_key in ["intent_extraction", "routing_payload", "routing_hint"]:
            source = metadata.get(source_key)
            if not source:
                continue

            agent_val = (
                getattr(source, "role", None)
                or getattr(source, "agent", None)
                or (source.get("role") if isinstance(source, dict) else None)
                or (source.get("agent") if isinstance(source, dict) else None)
                or (source.get("target_role") if isinstance(source, dict) else None)
                or (source.get("target_agent") if isinstance(source, dict) else None)
            )
            if agent_val:
                candidates.add(str(getattr(agent_val, "value", agent_val)).lower())

        # 2. Extract explicit overrides
        override = metadata.get("role_override") or metadata.get("agent_override")
        if override:
            candidates.add(str(getattr(override, "value", override)).lower())

        # 3. Query DB Semantic Matcher
        if hasattr(self.librarian, "search_skills"):
            try:
                matched_results = self.librarian.search_skills(prompt)
                if matched_results:
                    matched_agents = [
                        res.get("role_id") or res.get("agent_id")
                        for res in matched_results
                        if isinstance(res, dict) and (res.get("role_id") or res.get("agent_id"))
                    ]
                    if matched_agents:
                        logger.info(
                            f"[Discovery] Fast-path DB hit for prompt: Matched agents/roles -> {matched_agents}"
                        )
                        return matched_agents
            except Exception as err:
                logger.warning(f"[Discovery] Skill matching probe failed gracefully: {err}")

        # 4. Query registered DB roles
        if not candidates and hasattr(self.librarian, "list_registered_roles"):
            try:
                registered = self.librarian.list_registered_roles()
                if registered:
                    candidates.update(registered)
            except Exception as err:
                logger.warning(f"[Discovery] Error querying registered roles from DB: {err}")

        # 5. Last resort: in-memory registered agents
        if not candidates:
            candidates.update(self.agents.keys())

        return list(candidates)

    def _details_to_contract(
        self, details: Dict[str, Any], fallback_agent: Any
    ) -> Optional[CapabilityContract]:
        """Converts raw librarian action details into a formal CapabilityContract object if ACTIVE."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            logger.debug(f"[Discovery] Skipping inactive capability '{details.get('action_name')}'")
            return None

        raw_agent = (
            details.get("role")
            or details.get("agent")
            or details.get("primary_role_id")
            or details.get("primary_agent_id")
        )
        fallback_str = str(getattr(fallback_agent, "value", fallback_agent)).lower()
        target_agent = str(getattr(raw_agent, "value", raw_agent)).lower() if raw_agent else fallback_str

        esc_level = details.get("escalation_level")
        if esc_level is None:
            esc_level = get_default_escalation_level()

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []

        return CapabilityContract(
            capability_name=details.get("capability_name", details.get("action_name", "")),
            agent=target_agent,
            description=details.get("description", ""),
            consumed_artifacts=details.get("consumed_artifacts", []),
            produced_artifacts=details.get("produced_artifacts", []),
            escalation_level=esc_level,
            required_binaries=req_binaries,
        )

    def _build_agent_profiles(
        self, candidate_agents: List[Any]
    ) -> Dict[str, AgentProfile]:
        """Builds AgentProfiles populated with active capabilities from DB and live system binary checks."""
        profiles: Dict[str, AgentProfile] = {}

        for agent in candidate_agents:
            agent_str = str(getattr(agent, "value", agent)).lower()

            try:
                manifest = get_agent_manifest(agent_str)
            except Exception:
                manifest = None

            if isinstance(manifest, dict):
                manifest_name = manifest.get("name", agent_str.capitalize())
                default_action = manifest.get("default_action")
            else:
                manifest_name = getattr(manifest, "name", agent_str.capitalize())
                default_action = getattr(manifest, "default_action", None)

            action_names: List[str] = []
            if hasattr(self.librarian, "list_available_actions"):
                try:
                    action_names = self.librarian.list_available_actions(agent_str) or []
                except Exception as err:
                    logger.warning(f"[Discovery] DB Error listing actions for '{agent_str}': {err}")

            cap_dict: Dict[str, CapabilityContract] = {}
            for name in action_names:
                details = self.librarian.get_action_details(name)
                if details:
                    contract = self._details_to_contract(details, agent_str)
                    if contract:
                        cap_dict[contract.capability_name] = contract

            if default_action:
                default_details = self.librarian.get_action_details(default_action)
                if default_details:
                    default_contract = self._details_to_contract(default_details, agent_str)
                    if default_contract and default_contract.capability_name not in cap_dict:
                        cap_dict[default_contract.capability_name] = default_contract

            is_healthy = True
            health_info: Dict[str, Any] = {"healthy": True, "status": "Operational"}
            agent_instance = self.agents.get(agent_str)

            if agent_instance and hasattr(agent_instance, "probe"):
                try:
                    probe_data = agent_instance.probe(probe_type="full")
                    health_info = probe_data.get("health", health_info)
                    is_healthy = bool(health_info.get("healthy", True))

                    probed_caps = probe_data.get("capabilities", {}).get("actions", {})
                    if isinstance(probed_caps, dict):
                        for cap_key in probed_caps.keys():
                            if cap_key not in cap_dict:
                                details = self.librarian.get_action_details(cap_key)
                                if details:
                                    contract = self._details_to_contract(details, agent_str)
                                    if contract:
                                        cap_dict[cap_key] = contract
                except Exception as e:
                    logger.error(f"[Discovery] Runtime probe faulted for '{agent_str}': {e}")
                    is_healthy = False
                    health_info = {"healthy": False, "status": f"Probe Exception: {e}"}

            verified_bins: Set[str] = set()
            missing_bins: Set[str] = set()

            for cap in cap_dict.values():
                for binary in cap.required_binaries:
                    if shutil.which(binary):
                        verified_bins.add(binary)
                    else:
                        missing_bins.add(binary)

            profiles[agent_str] = AgentProfile(
                agent=agent_str,
                name=manifest_name,
                manifest=manifest,
                capabilities=cap_dict,
                verified_binaries=verified_bins,
                missing_binaries=missing_bins,
                is_healthy=is_healthy,
                health_status=health_info,
            )

        return profiles

    def discover_equipped_agent(
        self, requirement: UnfulfilledRequirement, blackboard: TaskBlackboard
    ) -> Tuple[AgentProfile, CapabilityContract]:
        """
        Finds an active agent profile equipped to handle the given requirement.
        Fails hard immediately if missing system roles, unmapped fallback actions, or unequipped agents occur.
        """
        target_cap_name = requirement.capability_required
        available_artifacts = blackboard.available_artifact_keys

        target_details = self.librarian.get_action_details(target_cap_name)

        # 1. Direct role/agent override lookup
        override_agent = getattr(requirement, "assigned_role_override", None) or getattr(
            requirement, "assigned_agent_override", None
        )
        if override_agent:
            target_str = str(getattr(override_agent, "value", override_agent)).lower()
            profile = self._ensure_profile_active(target_str)
            if profile:
                cap_contract = profile.capabilities.get(target_cap_name) or (
                    self._details_to_contract(target_details, target_str) if target_details else None
                )
                if cap_contract:
                    if target_cap_name not in profile.capabilities:
                        profile.capabilities[target_cap_name] = cap_contract

                    equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                    equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                    if equipped:
                        return profile, cap_contract

        # 2. Direct action owner lookup from DB metadata
        if target_details:
            owner_val = (
                target_details.get("role")
                or target_details.get("agent")
                or target_details.get("primary_role_id")
                or target_details.get("primary_agent_id")
            )
            if owner_val:
                owner_str = str(getattr(owner_val, "value", owner_val)).lower()
                profile = self._ensure_profile_active(owner_str)
                if profile:
                    contract = self._details_to_contract(target_details, owner_str)
                    if contract:
                        cap_contract = profile.capabilities.get(target_cap_name, contract)
                        if target_cap_name not in profile.capabilities:
                            profile.capabilities[target_cap_name] = cap_contract

                        equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                        equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                        if equipped:
                            return profile, cap_contract

        # 3. Check active profiles currently in memory
        for profile in self.active_profiles.values():
            if target_cap_name in profile.capabilities:
                equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                if equipped:
                    return profile, profile.capabilities[target_cap_name]

        # 4. CAPABILITY GAP DETECTED -> Escalate to System Engineer (Fail Fast if Unmapped)
        engineer_agent_id = None
        if hasattr(self.librarian, "resolve_agent_id_for_role"):
            engineer_agent_id = self.librarian.resolve_agent_id_for_role(FALLBACK_ENGINEER_ROLE)
            if not engineer_agent_id:
                engineer_agent_id = self.librarian.resolve_agent_id_for_role("default_system_engineer")

        if not engineer_agent_id and hasattr(self.librarian, "get_diagnostic_agent"):
            engineer_agent_id = self.librarian.get_diagnostic_agent()

        if not engineer_agent_id:
            raise RoleConfigurationError(
                f"[FATAL DISCOVERY FAULT] Required system role '{FALLBACK_ENGINEER_ROLE}' "
                f"is not mapped to an agent in 'system_roles'. Run database initialization/migrations."
            )

        escalation_lvl = EscalationLevel.L4_ENGINEER_FALLBACK

        logger.warning(
            f"[Discovery] Capability Gap Registered: No agent equipped for '{target_cap_name}'. "
            f"Escalating requirement to Level {int(escalation_lvl)} fallback agent: '{engineer_agent_id}'."
        )

        blackboard.log_gap(f"Capability Gap: No active agent equipped for action '{target_cap_name}'")
        blackboard.set_artifact(
            "registered_capability_gap",
            {
                "missing_capability": target_cap_name,
                "requirement_params": getattr(requirement, "parameters", {}),
                "escalated_to_role": FALLBACK_ENGINEER_ROLE,
                "escalated_to_agent": engineer_agent_id,
            },
        )

        if hasattr(blackboard, "current_escalation_level"):
            blackboard.current_escalation_level = escalation_lvl

        engineer_profile = self._ensure_profile_active(engineer_agent_id)
        if not engineer_profile:
            raise RoleConfigurationError(
                f"[FATAL DISCOVERY FAULT] Mapped engineer agent '{engineer_agent_id}' "
                f"for role '{FALLBACK_ENGINEER_ROLE}' is not registered or active in 'agent_registry'."
            )

        # Dynamic fallback action resolution (Fail Fast if default_action missing from agent manifest/DB)
        engineer_action = None
        if hasattr(self.librarian, "get_agent_default_action") and callable(self.librarian.get_agent_default_action):
            engineer_action = self.librarian.get_agent_default_action(engineer_agent_id)

        if not engineer_action and engineer_profile.manifest:
            m = engineer_profile.manifest
            if isinstance(m, dict):
                engineer_action = m.get("default_action")
            else:
                engineer_action = getattr(m, "default_action", None)

        if not engineer_action:
            raise RoleConfigurationError(
                f"[FATAL DISCOVERY FAULT] Mapped engineer agent '{engineer_agent_id}' "
                f"has no 'default_action' configured in its manifest or database metadata."
            )

        eng_contract = engineer_profile.capabilities.get(engineer_action)
        if not eng_contract:
            details = self.librarian.get_action_details(engineer_action)
            if details:
                eng_contract = self._details_to_contract(details, engineer_agent_id)

        if not eng_contract:
            raise RoleConfigurationError(
                f"[FATAL DISCOVERY FAULT] Mapped engineer agent '{engineer_agent_id}' "
                f"default action '{engineer_action}' could not be resolved into a valid CapabilityContract."
            )

        if not hasattr(requirement, "parameters") or requirement.parameters is None:
            requirement.parameters = {}

        requirement.parameters["failed_action"] = target_cap_name
        requirement.parameters["failure_reason"] = "Capability Gap: No registered agent is equipped with this action."

        # Mutate requirement to route through resolved engineer agent and action
        requirement.capability_required = engineer_action
        requirement.assigned_role_override = FALLBACK_ENGINEER_ROLE
        requirement.assigned_agent_override = engineer_agent_id
        if hasattr(requirement, "escalation_level"):
            requirement.escalation_level = escalation_lvl

        return engineer_profile, eng_contract