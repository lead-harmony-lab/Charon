"""
charon/core/coordinator/engine.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Core Reflection Engine and Multi-Intent Coordinator Facade.
Orchestrates prompt decomposition, contract negotiations, dynamic agent discovery,
diagnostic gap dynamic re-routing, blueprint capturing, and stateful reflection loops
aligned with Revision 3 CBAC database schema & trigger guardrails.
Enforces canonical role & agent lookup via SkillLibrarian SSOT.
"""

import asyncio
import concurrent.futures
import inspect
import logging
import time
from typing import Any, Dict, Optional, Tuple, Union

from charon.agents.base import BaseAgent
from charon.core.contracts import (
    CapabilityNegotiation,
    ContractResponse,
    DiagnosticGap,
    ExecutionStatus,
    GapType,
    SkillBlueprint,
)
from charon.core.coordinator.blackboard import (
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.coordinator.decomposer import RequirementDecomposer
from charon.core.coordinator.discovery import AgentDiscoveryManager
from charon.core.coordinator.escalation import EscalationManager
from charon.core.coordinator.profile import (
    CapabilityContract,
    get_default_escalation_level,
)
from charon.core.skills import SkillLibrarian
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator")

MAX_LOOP_LIMIT = 25


def _resolve_agent_id(agent_or_role: Any) -> str:
    """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT."""
    if not agent_or_role:
        return ""

    role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
    if not role_str:
        return ""

    librarian = SkillLibrarian.get_instance()
    if hasattr(librarian, "resolve_agent_id_for_role") and callable(
        librarian.resolve_agent_id_for_role
    ):
        try:
            resolved = librarian.resolve_agent_id_for_role(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Engine] SkillLibrarian failed to resolve role '{role_str}': {err}")

    elif hasattr(librarian, "resolve_agent_id") and callable(librarian.resolve_agent_id):
        try:
            resolved = librarian.resolve_agent_id(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Engine] SkillLibrarian failed to resolve agent ID for '{role_str}': {err}")

    return role_str


def get_capability(
    capability_name: str, agent: Optional[Union[str, Any]] = None
) -> Optional[CapabilityContract]:
    """Dynamically resolves a CapabilityContract via SkillLibrarian, filtering for ACTIVE status."""
    librarian = SkillLibrarian.get_instance()
    details = librarian.get_action_details(capability_name)
    if not details:
        return None

    # Schema Compliance: Verify skill status is ACTIVE
    skill_status = details.get("status", "ACTIVE")
    if skill_status != "ACTIVE":
        logger.warning(
            f"[COORDINATOR] Skill '{capability_name}' requested but is currently in '{skill_status}' state."
        )
        return None

    # Schema Compliance: Resolve system roles -> active agent_id
    default_agent = (
        librarian.resolve_agent_id_for_role("system_fallback")
        if hasattr(librarian, "resolve_agent_id_for_role")
        else getattr(librarian, "get_system_fallback", lambda: "system_fallback")()
    )
    raw_agent = agent or details.get("primary_agent_id", default_agent)
    target_agent = _resolve_agent_id(raw_agent)

    return CapabilityContract(
        capability_name=details.get(
            "capability_name", details.get("action_name", capability_name)
        ),
        agent=target_agent,
        description=details.get("description", ""),
        consumed_artifacts=details.get("consumed_artifacts", []),
        produced_artifacts=details.get("produced_artifacts", []),
        escalation_level=details.get("escalation_level") or get_default_escalation_level(),
        required_binaries=details.get("system_requirements", details.get("required_binaries", [])),
    )


def _exec_sync_or_async(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Executes a function safely whether it is a synchronous method or an async coroutine function."""
    if inspect.iscoroutinefunction(func):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(func(*args, **kwargs)))
                return future.result()
        return asyncio.run(func(*args, **kwargs))

    result = func(*args, **kwargs)
    if inspect.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(result))
                return future.result()
        return asyncio.run(result)

    return result


class Coordinator:
    """The Reflection & Coordination Engine governing the Charon execution loop."""

    def __init__(self, agents: Optional[Dict[Union[str, Any], BaseAgent]] = None) -> None:
        self.discovery = AgentDiscoveryManager()
        self.decomposer = RequirementDecomposer()
        self.escalator = EscalationManager()

        if agents:
            for key, instance in agents.items():
                self.register_agent(key, instance)

    @property
    def agents(self) -> Dict[Union[str, Any], BaseAgent]:
        return self.discovery.agents

    @property
    def active_profiles(self) -> Dict[Union[str, Any], Any]:
        return self.discovery.active_profiles

    def register_agent(self, agent_key: Union[str, Any], agent_instance: BaseAgent) -> None:
        canonical_key = _resolve_agent_id(agent_key)
        self.discovery.register_agent(canonical_key, agent_instance)

    def probe_agent(self, agent: Union[str, Any], probe_type: str = "full") -> Dict[str, Any]:
        canonical_key = _resolve_agent_id(agent)
        return self.discovery.probe_agent(canonical_key, probe_type=probe_type)

    def probe_all_agents(self, probe_type: str = "full") -> Dict[str, Dict[str, Any]]:
        return self.discovery.probe_all_agents(probe_type=probe_type)

    def _get_diagnostic_engineer(self) -> str:
        """Resolves the diagnostic engineer agent ID via system_roles table lookup."""
        librarian = SkillLibrarian.get_instance()

        if hasattr(librarian, "get_diagnostic_agent") and callable(librarian.get_diagnostic_agent):
            res = librarian.get_diagnostic_agent()
            if res:
                return _resolve_agent_id(res)

        if hasattr(librarian, "resolve_agent_id_for_role") and callable(librarian.resolve_agent_id_for_role):
            res = librarian.resolve_agent_id_for_role("system_engineer")
            if res:
                return _resolve_agent_id(res)

        for agent_id, agent_obj in self.agents.items():
            if getattr(agent_obj, "is_active", True):
                return _resolve_agent_id(agent_id)

        return "system_engineer"

    def _get_agent_default_action(self, agent_id: str) -> str:
        """Dynamically resolves default interface action for an agent_id via SkillLibrarian.

        Raises:
            ValueError: If the target agent manifest does not define a default_action.
        """
        canonical_agent = _resolve_agent_id(agent_id)
        librarian = SkillLibrarian.get_instance()

        if hasattr(librarian, "get_agent_default_action") and callable(librarian.get_agent_default_action):
            action = librarian.get_agent_default_action(canonical_agent)
            if action:
                return str(action)

        manifest = (
            librarian.get_agent_manifest(canonical_agent)
            if hasattr(librarian, "get_agent_manifest")
            else None
        )
        if isinstance(manifest, dict) and manifest.get("default_action"):
            return str(manifest["default_action"])
        elif manifest and getattr(manifest, "default_action", None):
            return str(getattr(manifest, "default_action"))

        raise ValueError(
            f"[COORDINATOR ERROR] Cannot route task to agent '{canonical_agent}': "
            "Agent manifest is missing a required 'default_action' contract."
        )

    def initialize_blackboard(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskBlackboard:
        """Decomposes prompt, builds agent profiles, and initializes TaskBlackboard."""
        metadata = metadata or {}
        engine_task_id = task_id or metadata.get("task_id")

        kwargs: Dict[str, Any] = {
            "original_prompt": prompt,
            "status": TaskStatus.IN_PROGRESS,
            "metadata": metadata,
        }

        if engine_task_id:
            kwargs["task_id"] = engine_task_id

        blackboard = TaskBlackboard(**kwargs)

        profiles = self.discovery.preplan_and_build_profiles(prompt, metadata)
        blackboard.set_artifact("active_agent_profiles", [p.name for p in profiles.values()])

        self.decomposer.decompose(prompt, blackboard, metadata=metadata)
        return blackboard

    def select_next_execution_step(
        self, blackboard: TaskBlackboard
    ) -> Optional[Tuple[UnfulfilledRequirement, CapabilityContract, Dict[str, Any]]]:
        """Selects the next executable step using agent discovery and dependency resolution."""
        if not blackboard.unfulfilled_requirements:
            return None

        req = blackboard.unfulfilled_requirements[0]
        discovery_match = self.discovery.discover_equipped_agent(req, blackboard)

        if not discovery_match:
            capability = get_capability(req.capability_required)
            if capability:
                missing = [art for art in capability.consumed_artifacts if not blackboard.has_artifact(art)]
                if missing:
                    for idx, cand_req in enumerate(blackboard.unfulfilled_requirements[1:], start=1):
                        cand_cap = get_capability(cand_req.capability_required)
                        if cand_cap and any(art in cand_cap.produced_artifacts for art in missing):
                            promoted = blackboard.unfulfilled_requirements.pop(idx)
                            blackboard.unfulfilled_requirements.insert(0, promoted)
                            return self.select_next_execution_step(blackboard)

            self.escalator.escalate(
                blackboard, req, f"No equipped agent discovered for capability '{req.capability_required}'."
            )
            return None

        profile, capability = discovery_match
        bound_params = dict(req.parameters)
        for art_key in capability.consumed_artifacts:
            bound_params[art_key] = blackboard.get_artifact(art_key)

        if req.preferred_tool:
            bound_params["preferred_tool"] = req.preferred_tool

        return req, capability, bound_params

    def negotiate_contract(
        self, agent: Union[str, Any], requirement: UnfulfilledRequirement, blackboard: TaskBlackboard
    ) -> ContractResponse:
        """Conducts pre-turn contract negotiation with target agent and logs trace telemetry."""
        agent_key = _resolve_agent_id(agent)
        agent_instance = self.agents.get(agent_key) or self.agents.get(agent)
        agent_name = getattr(agent_instance, "name", agent_key)

        if agent_instance and hasattr(agent_instance, "is_active") and not agent_instance.is_active:
            engineer_agent_id = self._get_diagnostic_engineer()
            return ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.INCAPABLE,
                reason=f"Agent '{agent_name}' is inactive (DB Guard Constraint).",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Target agent '{agent_name}' is deactivated in agent_registry.",
                    suggested_remediation=f"Re-route task to active engineer ({engineer_agent_id}).",
                ),
            )

        negotiation = CapabilityNegotiation(
            agent_name=agent_name,
            target_action=requirement.capability_required,
            parameters=requirement.parameters,
            context_keys_available=list(blackboard.available_artifact_keys),
        )

        if not agent_instance:
            engineer_agent_id = self._get_diagnostic_engineer()
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.INCAPABLE,
                reason=f"Agent '{agent_name}' not registered.",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Target agent '{agent_name}' is not registered in runtime.",
                    suggested_remediation=f"Re-route task to fallback engineer ({engineer_agent_id}) or register target agent.",
                ),
            )
        else:
            if hasattr(agent_instance, "evaluate_capability"):
                response = _exec_sync_or_async(agent_instance.evaluate_capability, negotiation)
            else:
                response = ContractResponse(
                    agent_name=agent_instance.name,
                    status=ExecutionStatus.SATISFIED,
                    accomplishments=["Default capability negotiation validation passed."],
                )

        if response.status == ExecutionStatus.INCAPABLE and response.diagnostics:
            logger.info(
                f"[COORDINATOR] Negotiation Gap ({response.diagnostics.gap_type.value}): "
                f"{response.diagnostics.description}"
            )

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.NEGOTIATION,
                agent_name=agent_name,
                action=requirement.capability_required,
                details={
                    "status": response.status.value,
                    "reason": response.reason,
                    "requirement_id": requirement.requirement_id,
                    "escalation_level": requirement.escalation_level.value,
                    "diagnostics": response.diagnostics.model_dump() if response.diagnostics else None,
                },
            )
        )
        return response

    def execute_contract_step(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        capability: CapabilityContract,
        parameters: Dict[str, Any],
    ) -> ContractResponse:
        """Executes negotiated contract step, evaluates DiagnosticGap payloads, logs blueprints,
        and triggers auto-rerouting or escalation as required.
        """
        override_agent = getattr(requirement, "assigned_agent_override", None)
        if override_agent:
            target_agent_key = _resolve_agent_id(override_agent)
        else:
            target_agent_key = _resolve_agent_id(capability.agent)

        agent_instance = self.agents.get(target_agent_key) or self.agents.get(override_agent or capability.agent)
        agent_name = getattr(agent_instance, "name", target_agent_key)

        if not agent_instance:
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.FAILED,
                reason=f"No live agent instance registered for {target_agent_key}.",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Agent ID '{target_agent_key}' has no active instance registered.",
                ),
            )
            blackboard.record_contract_response(response, action=requirement.capability_required)
            self._handle_step_failure(blackboard, requirement, target_agent_key, response)
            return response

        negotiation = CapabilityNegotiation(
            agent_name=agent_name,
            target_action=requirement.capability_required,
            parameters=parameters,
            context_keys_available=list(blackboard.available_artifact_keys),
        )

        start_time = time.perf_counter()
        try:
            if hasattr(agent_instance, "process_contract"):
                response = _exec_sync_or_async(
                    agent_instance.process_contract,
                    negotiation=negotiation,
                    raw_prompt=blackboard.original_prompt,
                )
            else:
                res = _exec_sync_or_async(
                    agent_instance.execute,
                    action=requirement.capability_required,
                    parameters=parameters,
                    raw_prompt=blackboard.original_prompt,
                )
                response = ContractResponse(
                    agent_name=agent_name,
                    status=ExecutionStatus.SATISFIED,
                    accomplishments=[str(res)[:300] if res else "Executed successfully."],
                )
        except Exception as exc:
            engineer_agent_id = self._get_diagnostic_engineer()
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.FAILED,
                reason=str(exc),
                diagnostics=DiagnosticGap(
                    gap_type=GapType.EXECUTION_ERROR,
                    description=f"Unhandled exception during contract execution: {str(exc)}",
                    suggested_remediation=f"Re-route to {engineer_agent_id} for ad-hoc repair.",
                ),
            )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        produced_map = {}

        is_success = response.status in (ExecutionStatus.SATISFIED, ExecutionStatus.SUCCESS)

        if capability.produced_artifacts and is_success:
            for art_key in capability.produced_artifacts:
                if blackboard.has_artifact(art_key):
                    produced_map[art_key] = blackboard.get_artifact(art_key)

        if response.skill_blueprint:
            logger.info(
                f"[COORDINATOR] Captured SkillBlueprint '{response.skill_blueprint.suggested_skill_name}' "
                f"from {agent_name}."
            )
            blackboard.set_artifact(
                f"blueprint_{response.skill_blueprint.action_name}",
                response.skill_blueprint.model_dump(),
            )

        blackboard.record_contract_response(
            response=response,
            action=requirement.capability_required,
            produced_artifacts_map=produced_map,
        )

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.EXECUTION,
                agent_name=agent_name,
                action=requirement.capability_required,
                duration_ms=duration_ms,
                details={
                    "status": response.status.value,
                    "produced_artifacts": list(produced_map.keys()),
                    "reason": response.reason,
                    "accomplishments": response.accomplishments,
                    "diagnostics": response.diagnostics.model_dump() if response.diagnostics else None,
                    "has_blueprint": response.skill_blueprint is not None,
                },
            )
        )

        if is_success:
            blackboard.pop_requirement(requirement.requirement_id)
        else:
            self._handle_step_failure(blackboard, requirement, target_agent_key, response)

        return response

    def _handle_step_failure(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        current_agent: Union[str, Any],
        response: ContractResponse,
    ) -> None:
        """Evaluates step failure and DiagnosticGap to perform dynamic re-routing or escalation."""
        agent_str = _resolve_agent_id(current_agent)
        diag = response.diagnostics
        engineer_agent_id = self._get_diagnostic_engineer()

        if diag and diag.gap_type == GapType.MISSING_TOOL:
            librarian = SkillLibrarian.get_instance()
            if hasattr(librarian, "record_skill_gap"):
                librarian.record_skill_gap(
                    action_name=requirement.capability_required,
                    requesting_agent=agent_str,
                    missing_prerequisites=requirement.parameters.get("missing_prerequisites", []),
                )

        if agent_str != engineer_agent_id and (
            not diag or diag.gap_type in [GapType.MISSING_TOOL, GapType.AGENT_INCAPABLE, GapType.EXECUTION_ERROR]
        ):
            logger.warning(
                f"[COORDINATOR] Auto-rerouting requirement '{requirement.requirement_id}' "
                f"from {agent_str} -> {engineer_agent_id} due to diagnostic gap: "
                f"{diag.description if diag else response.reason}"
            )

            if not hasattr(requirement, "parameters") or requirement.parameters is None:
                requirement.parameters = {}
            requirement.parameters["failed_action"] = requirement.capability_required
            requirement.parameters["failure_reason"] = diag.description if diag else response.reason
            requirement.capability_required = self._get_agent_default_action(engineer_agent_id)
            requirement.assigned_agent_override = engineer_agent_id
            return

        self.escalator.escalate(
            blackboard,
            requirement,
            response.reason or "Contract step execution failed.",
        )

    def run_turn(self, blackboard: TaskBlackboard) -> TaskBlackboard:
        """Executes full reflection loop, dispatching steps and publishing telemetry events."""
        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.SYSTEM,
                agent_name="Coordinator",
                action="run_turn_start",
                details={
                    "task_id": str(blackboard.task_id),
                    "pending_requirements": len(blackboard.unfulfilled_requirements),
                    "available_artifacts": list(blackboard.available_artifact_keys),
                },
            )
        )

        step_count = 0
        engineer_agent_id = self._get_diagnostic_engineer()

        while (
            blackboard.status in (TaskStatus.IN_PROGRESS, TaskStatus.NEEDS_ESCALATION)
            and blackboard.unfulfilled_requirements
            and step_count < MAX_LOOP_LIMIT
        ):
            if blackboard.status == TaskStatus.NEEDS_ESCALATION:
                blackboard.status = TaskStatus.IN_PROGRESS

            step_tuple = self.select_next_execution_step(blackboard)
            if not step_tuple:
                break

            req, cap, params = step_tuple
            step_count += 1

            override_agent = getattr(req, "assigned_agent_override", None)
            if override_agent:
                target_agent = override_agent
            else:
                target_agent = cap.agent

            negotiation_resp = self.negotiate_contract(target_agent, req, blackboard)
            if negotiation_resp.status == ExecutionStatus.INCAPABLE:
                target_str = _resolve_agent_id(target_agent)
                if target_str != engineer_agent_id:
                    logger.warning(
                        f"[COORDINATOR] Agent {target_str} incapable during negotiation. "
                        f"Overriding requirement target to {engineer_agent_id}."
                    )

                    if not hasattr(req, "parameters") or req.parameters is None:
                        req.parameters = {}
                    req.parameters["failed_action"] = req.capability_required
                    req.parameters["failure_reason"] = negotiation_resp.reason or "Agent incapable of action."
                    req.capability_required = self._get_agent_default_action(engineer_agent_id)
                    req.assigned_agent_override = engineer_agent_id
                    continue

                self.escalator.escalate(
                    blackboard, req, negotiation_resp.reason or "Agent incapable of action."
                )
                continue

            self.execute_contract_step(blackboard, req, cap, params)

        if not blackboard.unfulfilled_requirements and blackboard.status == TaskStatus.IN_PROGRESS:
            blackboard.status = TaskStatus.COMPLETED

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.SYSTEM,
                agent_name="Coordinator",
                action="run_turn_complete",
                details={
                    "task_id": str(blackboard.task_id),
                    "final_status": blackboard.status.value,
                    "total_steps_executed": step_count,
                    "remaining_requirements": len(blackboard.unfulfilled_requirements),
                },
            )
        )

        return blackboard