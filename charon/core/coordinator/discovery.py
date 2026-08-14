"""
charon/core/coordinator/discovery.py
System Version: v0.9.0 | File Revision: 9.0.0

Module: Coordinator Agent & Role Discovery & Probing Manager.
Refactored for the Active Execution Envelope (Work Contract) paradigm.
Handles agent registration, envelope capability verification, and strict dynamic profile building.
Enforces absolute zero-fallback execution: raises fast RoleConfigurationError exceptions
if a Work Contract envelope cannot be resolved or is unequipped.
"""

import logging
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple

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
    """Raised when a required system role, Work Contract, or agent capability cannot be strictly resolved."""


class AgentDiscoveryManager:
    """Manages agent/role registration, health probing, and dynamic profile resolution. Zero fallbacks."""

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

        for method in ("resolve_agent_id_for_role", "resolve_agent_id"):
            if hasattr(self.librarian, method) and callable(getattr(self.librarian, method)):
                try:
                    resolved = getattr(self.librarian, method)(role_str)
                    if resolved:
                        return str(resolved).strip()
                except Exception as err:
                    logger.debug(f"[Discovery] SkillLibrarian failed {method} for '{role_str}': {err}")

        return role_str

    def register_agent(self, agent_key: Any, agent_instance: BaseAgent) -> None:
        """Registers a live BaseAgent instance with the Coordinator discovery pool."""
        agent_str = self._resolve_agent_id(agent_key)
        if not agent_str:
            raise RoleConfigurationError("[Discovery] Cannot register agent instance with empty agent identifier.")

        # Ensure the agent has the new Active Execution Envelope interface
        if not hasattr(agent_instance, "execute_task"):
            raise RoleConfigurationError(
                f"[Discovery] FATAL: Agent '{agent_str}' lacks execute_task() Envelope interface."
            )

        self.agents[agent_str] = agent_instance
        logger.info(
            f"[Discovery] Registered live envelope executor for '{agent_str}' ({getattr(agent_instance, 'name', 'unnamed')})"
        )

    def probe_agent(self, agent: Any, probe_type: str = "full") -> Dict[str, Any]:
        """Probes a specific registered agent instance for runtime health and Work Contract schemas."""
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

        logger.info(f"[Discovery] Performing on-demand hydration for unplanned envelope '{agent_str}'.")
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
                    for res in matched_results:
                        if isinstance(res, dict):
                            resolved_id = self._resolve_agent_id(res.get("role_id") or res.get("agent_id"))
                            if resolved_id:
                                candidates.add(resolved_id)
            except Exception as err:
                logger.warning(f"[Discovery] Envelope matching probe failed gracefully: {err}")

        # 4. Fallback: Check in-memory registered agents pool
        if not candidates:
            candidates.update(self.agents.keys())

        return list(candidates)

    def _details_to_contract(
        self, details: Dict[str, Any], target_agent: str
    ) -> Optional[CapabilityContract]:
        """Converts raw librarian Work Contract metadata into a formal CapabilityContract object if ACTIVE."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            logger.debug(f"[Discovery] Skipping inactive Work Contract '{details.get('action_name')}'")
            return None

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
        """Builds AgentProfiles focusing strictly on Work Contract envelopes via SkillLibrarian."""
        profiles: Dict[str, AgentProfile] = {}

        for agent in candidate_agents:
            agent_str = self._resolve_agent_id(agent)
            if not agent_str:
                continue

            try:
                manifest = get_agent_manifest(agent_str)
            except Exception:
                manifest = None

            manifest_name = agent_str
            default_action = None
            if isinstance(manifest, dict):
                manifest_name = manifest.get("name", agent_str)
                default_action = manifest.get("default_action")
            elif manifest:
                manifest_name = getattr(manifest, "name", agent_str)
                default_action = getattr(manifest, "default_action", None)

            cap_dict: Dict[str, CapabilityContract] = {}

            # 1. Register the Default Action (The Work Contract Envelope)
            if default_action:
                default_details = self.librarian.get_action_details(default_action)
                if default_details:
                    default_contract = self._details_to_contract(default_details, agent_str)
                    if default_contract:
                        cap_dict[default_contract.capability_name] = default_contract

            is_healthy = True
            health_info: Dict[str, Any] = {"healthy": True, "status": "Operational"}
            agent_instance = self.agents.get(agent_str)

            # 2. Probe actual instance state and dynamic schema capabilities
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
                    logger.error(f"[Discovery] Runtime envelope probe faulted for '{agent_str}': {e}")
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
        Finds an active agent profile equipped to handle the Work Contract requirement.
        Strict Zero-Fallback Policy: Raises a RoleConfigurationError immediately if
        no agent can be resolved or if mandatory schema/artifacts are unmet.
        """
        target_envelope = requirement.capability_required
        available_artifacts = blackboard.available_artifact_keys

        # 1. Resolve Target Agent ID
        resolved_agent_id = None
        override = getattr(requirement, "assigned_role_override", None) or getattr(
            requirement, "assigned_agent_override", None
        )

        if override:
            resolved_agent_id = self._resolve_agent_id(override)
        else:
            # Query Librarian to find which Agent owns this specific Work Contract Envelope
            target_details = self.librarian.get_action_details(target_envelope)
            if target_details:
                raw_owner = (
                    target_details.get("primary_agent_id")
                    or target_details.get("agent_id")
                    or target_details.get("role")
                    or target_details.get("agent")
                )
                if raw_owner:
                    resolved_agent_id = self._resolve_agent_id(raw_owner)

            if not resolved_agent_id:
                for method in ("get_agents_for_action", "resolve_agents_for_action"):
                    if hasattr(self.librarian, method) and callable(getattr(self.librarian, method)):
                        res = getattr(self.librarian, method)(target_envelope)
                        if res:
                            resolved_agent_id = self._resolve_agent_id(res[0] if isinstance(res, list) else res)
                            break

        if not resolved_agent_id:
            gap_msg = f"Orphaned Envelope: No registered agent maps to Work Contract '{target_envelope}'."
            blackboard.log_gap(gap_msg)
            raise RoleConfigurationError(f"[FATAL DISCOVERY FAULT] {gap_msg}")

        # 2. Ensure Profile is Active
        profile = self._ensure_profile_active(resolved_agent_id)
        if not profile:
            gap_msg = f"Inactive Envelope: Resolved agent '{resolved_agent_id}' is not hydrated in active profiles."
            blackboard.log_gap(gap_msg)
            raise RoleConfigurationError(f"[FATAL DISCOVERY FAULT] {gap_msg}")

        # 3. Ensure Capability Contract Exists
        contract = profile.capabilities.get(target_envelope)
        if not contract:
            # Attempt a final JIT lookup from DB
            target_details = self.librarian.get_action_details(target_envelope)
            if target_details:
                contract = self._details_to_contract(target_details, resolved_agent_id)
                if contract:
                    profile.capabilities[target_envelope] = contract

        if not contract:
            gap_msg = f"Contract Mismatch: Agent '{resolved_agent_id}' lacks mapped capability '{target_envelope}'."
            blackboard.log_gap(gap_msg)
            raise RoleConfigurationError(f"[FATAL DISCOVERY FAULT] {gap_msg}")

        # 4. Enforce Equipment & Artifact Readiness (Fast-Fail)
        equip_res = profile.is_equipped(target_envelope, available_artifacts)
        is_equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)

        if not is_equipped:
            gap_msg = f"Unmet Constraints: Agent '{resolved_agent_id}' cannot execute '{target_envelope}' due to missing artifacts or binaries."
            blackboard.log_gap(gap_msg)
            raise RoleConfigurationError(f"[FATAL DISCOVERY FAULT] {gap_msg}")

        return profile, contract