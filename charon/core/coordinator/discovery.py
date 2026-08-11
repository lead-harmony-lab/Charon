"""
charon/core/coordinator/discovery.py
System Version: v0.8.0 | File Revision: 8.1.0

Module: Coordinator Agent & Role Discovery & Probing Manager.
Handles agent and role registration, candidate preplanning, live capability probing,
host binary availability verification, and dynamic profile building.
Enforces strict zero-fallback execution: raises fast RoleConfigurationError exceptions
if skill metadata or agent capabilities cannot be resolved via SkillLibrarian.
"""

import logging
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from charon.agents.base import BaseAgent
from charon.core.coordinator.blackboard import TaskBlackboard, UnfulfilledRequirement
from charon.core.coordinator.profile import (
    AgentProfile,
    CapabilityContract,
    get_default_escalation_level,
)
from charon.core.skills.librarian import SkillLibrarian

# Safe import for manifest lookup
try:
    from charon.intent.manifests import get_agent_manifest
except ImportError:
    get_agent_manifest = lambda agent_id: None

logger = logging.getLogger("charon.core.coordinator.discovery")


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role, agent capability, or action contract cannot be strictly resolved."""


class AgentDiscoveryManager:
    """Manages agent/role registration, health probing, and dynamic profile resolution without magic fallbacks."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.agents: Dict[str, BaseAgent] = {}
        self.active_profiles: Dict[str, AgentProfile] = {}

    def _resolve_agent_id(self, agent_or_role: Any) -> str:
        """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT."""
        if not agent_or_role:
            return ""

        role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
        if not role_str:
            return ""

        if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(
            self.librarian.resolve_agent_id_for_role
        ):
            try:
                resolved = self.librarian.resolve_agent_id_for_role(role_str)
                if resolved:
                    return str(resolved).strip()
            except Exception as err:
                logger.debug(f"[Discovery] SkillLibrarian failed to resolve role '{role_str}': {err}")

        elif hasattr(self.librarian, "resolve_agent_id") and callable(
            self.librarian.resolve_agent_id
        ):
            try:
                resolved = self.librarian.resolve_agent_id(role_str)
                if resolved:
                    return str(resolved).strip()
            except Exception as err:
                logger.debug(f"[Discovery] SkillLibrarian failed to resolve agent ID for '{role_str}': {err}")

        return role_str

    def register_agent(self, agent_key: Any, agent_instance: BaseAgent) -> None:
        """Registers a live BaseAgent instance with the Coordinator discovery pool."""
        agent_str = self._resolve_agent_id(agent_key)
        if not agent_str:
            raise RoleConfigurationError("[Discovery] Cannot register agent instance with empty agent identifier.")

        self.agents[agent_str] = agent_instance
        logger.info(
            f"[Discovery] Registered live agent instance for '{agent_str}' ({getattr(agent_instance, 'name', 'unnamed')})"
        )

    def probe_agent(self, agent: Any, probe_type: str = "full") -> Dict[str, Any]:
        """Probes a specific registered agent instance for runtime health and dynamic capabilities."""
        agent_str = self._resolve_agent_id(agent)
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
        agent_str = self._resolve_agent_id(agent)
        if not agent_str:
            return None

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
                resolved = self._resolve_agent_id(agent_val)
                if resolved:
                    candidates.add(resolved)

        # 2. Extract explicit overrides
        override = metadata.get("role_override") or metadata.get("agent_override")
        if override:
            resolved_override = self._resolve_agent_id(override)
            if resolved_override:
                candidates.add(resolved_override)

        # 3. Query DB Semantic Matcher
        if hasattr(self.librarian, "search_skills") and callable(self.librarian.search_skills):
            try:
                matched_results = self.librarian.search_skills(prompt)
                if matched_results:
                    matched_agents = [
                        self._resolve_agent_id(res.get("role_id") or res.get("agent_id"))
                        for res in matched_results
                        if isinstance(res, dict) and (res.get("role_id") or res.get("agent_id"))
                    ]
                    matched_agents = [a for a in matched_agents if a]
                    if matched_agents:
                        logger.info(
                            f"[Discovery] Fast-path DB hit for prompt: Matched agents -> {matched_agents}"
                        )
                        return matched_agents
            except Exception as err:
                logger.warning(f"[Discovery] Skill matching probe failed gracefully: {err}")

        # 4. Query registered DB roles
        if not candidates and hasattr(self.librarian, "list_registered_roles") and callable(
            self.librarian.list_registered_roles
        ):
            try:
                registered = self.librarian.list_registered_roles()
                if registered:
                    candidates.update(
                        resolved
                        for resolved in (self._resolve_agent_id(r) for r in registered)
                        if resolved
                    )
            except Exception as err:
                logger.warning(f"[Discovery] Error querying registered roles from DB: {err}")

        # 5. Check in-memory registered agents pool
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
            or details.get("agent_id")
        )
        fallback_str = self._resolve_agent_id(fallback_agent)
        target_agent = self._resolve_agent_id(raw_agent) if raw_agent else fallback_str

        esc_level = details.get("escalation_level")
        if esc_level is None:
            esc_level = get_default_escalation_level()

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []
        cap_name = details.get("action_name") or details.get("capability_name") or details.get("skill_id", "")

        return CapabilityContract(
            capability_name=cap_name,
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
        """Builds AgentProfiles populated strictly with capabilities resolved via SkillLibrarian."""
        profiles: Dict[str, AgentProfile] = {}

        for agent in candidate_agents:
            agent_str = self._resolve_agent_id(agent)
            if not agent_str:
                continue

            try:
                manifest = get_agent_manifest(agent_str)
            except Exception:
                manifest = None

            if isinstance(manifest, dict):
                manifest_name = manifest.get("name", agent_str)
                default_action = manifest.get("default_action")
            else:
                manifest_name = getattr(manifest, "name", agent_str)
                default_action = getattr(manifest, "default_action", None)

            action_names: List[str] = []
            if hasattr(self.librarian, "list_available_actions") and callable(
                self.librarian.list_available_actions
            ):
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
                        if details.get("action_name"):
                            cap_dict[details["action_name"]] = contract
                        if details.get("skill_id"):
                            cap_dict[details["skill_id"]] = contract

            if default_action:
                default_details = self.librarian.get_action_details(default_action)
                if default_details:
                    default_contract = self._details_to_contract(default_details, agent_str)
                    if default_contract:
                        cap_dict[default_contract.capability_name] = default_contract
                        if default_details.get("action_name"):
                            cap_dict[default_details["action_name"]] = default_contract
                        if default_details.get("skill_id"):
                            cap_dict[default_details["skill_id"]] = default_contract

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
        Strict Zero-Fallback Policy: Raises a RoleConfigurationError immediately if
        no equipped agent or valid skill data can be resolved through SkillLibrarian.
        """
        target_cap_name = requirement.capability_required
        available_artifacts = blackboard.available_artifact_keys

        target_details = self.librarian.get_action_details(target_cap_name)

        # 1. Direct role/agent override lookup
        override_agent = getattr(requirement, "assigned_role_override", None) or getattr(
            requirement, "assigned_agent_override", None
        )
        if override_agent:
            target_str = self._resolve_agent_id(override_agent)
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

        # 2. Direct action owner or mapped agent lookup via SkillLibrarian
        candidate_agents: List[str] = []
        if target_details:
            raw_owners = (
                target_details.get("agents")
                or target_details.get("roles")
                or [
                    target_details.get(k)
                    for k in ("role", "agent", "primary_role_id", "primary_agent_id", "agent_id")
                    if target_details.get(k)
                ]
            )
            if isinstance(raw_owners, (str, bytes)):
                candidate_agents.append(str(raw_owners))
            elif isinstance(raw_owners, list):
                candidate_agents.extend([str(o) for o in raw_owners if o])

        for method_name in ("get_agents_for_action", "get_agents_for_skill", "resolve_agents_for_action"):
            if hasattr(self.librarian, method_name) and callable(getattr(self.librarian, method_name)):
                try:
                    res = getattr(self.librarian, method_name)(target_cap_name)
                    if res:
                        if isinstance(res, list):
                            candidate_agents.extend([str(x) for x in res if x])
                        elif isinstance(res, str):
                            candidate_agents.append(res)
                        break
                except Exception as err:
                    logger.debug(f"[Discovery] SkillLibrarian.{method_name} query failed: {err}")

        for c_agent in candidate_agents:
            c_str = self._resolve_agent_id(c_agent)
            if not c_str:
                continue
            profile = self._ensure_profile_active(c_str)
            if profile:
                contract = profile.capabilities.get(target_cap_name) or (
                    self._details_to_contract(target_details, c_str) if target_details else None
                )
                if contract:
                    if target_cap_name not in profile.capabilities:
                        profile.capabilities[target_cap_name] = contract

                    equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                    equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                    if equipped:
                        return profile, contract

        # 3. Check active profiles currently in memory (including manifest default actions)
        for profile in self.active_profiles.values():
            contract = profile.capabilities.get(target_cap_name)
            if not contract and target_details:
                manifest_default = None
                if isinstance(profile.manifest, dict):
                    manifest_default = profile.manifest.get("default_action")
                elif profile.manifest:
                    manifest_default = getattr(profile.manifest, "default_action", None)

                if manifest_default and str(manifest_default).lower() == str(target_cap_name).lower():
                    contract = self._details_to_contract(target_details, profile.agent)
                    if contract:
                        profile.capabilities[target_cap_name] = contract

            if contract:
                equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                if equipped:
                    return profile, contract

        # 4. CAPABILITY GAP DETECTED -> Fail Fast
        gap_msg = f"Capability Gap: No registered agent is equipped with action '{target_cap_name}'."
        blackboard.log_gap(gap_msg)

        raise RoleConfigurationError(
            f"[FATAL DISCOVERY FAULT] Required capability '{target_cap_name}' cannot be resolved to an equipped, "
            f"active agent. Ensure the skill is mapped in SkillLibrarian and that mandatory artifacts are available."
        )