"""
charon/core/coordinator/escalation.py
System Version: v0.9.0 | File Revision: 9.0.0

Module: Work Contract Escalation & Dynamic Constraint Injection Manager.
Evaluates DiagnosticArtifacts, enforces 2-attempt agent limits, injects dynamic
ConstraintRevision guardrails, and manages direct level jumps to Engineer Fallback.
Strictly relies on SkillLibrarian as DB SSOT.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.skills.librarian import SkillLibrarian
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator.escalation")


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role or default agent is not assigned in SkillLibrarian state."""


class ConstraintRevision(BaseModel):
    """Dynamic constraints injected into a Work Contract retry payload to close off failure pathways."""

    forbidden_actions: List[str] = Field(default_factory=list)
    required_adaptations: List[str] = Field(default_factory=list)
    failure_summary: str = ""
    diagnostic_context: Dict[str, Any] = Field(default_factory=dict)


class EscalationManager:
    """Manages failure evaluations, constraint revisions, and strict system escalations."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_target(
        self, details: Dict[str, Any], default_system_role: str
    ) -> Tuple[str, str]:
        """Resolves (role_name, agent_id) from action details or system_roles lookup via SkillLibrarian.

        Strictly relies on DB resolution without string mutation or synthetic fallbacks.
        Fails fast if the role or agent cannot be resolved from database state.
        """
        raw_role = (
            details.get("primary_role_id")
            or details.get("role")
            or default_system_role
        )
        if not raw_role:
            raise RoleConfigurationError(
                "[FATAL ESCALATION FAULT] No valid role identifier provided or resolved from action details."
            )

        role_name = str(getattr(raw_role, "value", raw_role)).strip()

        raw_agent = details.get("primary_agent_id") or details.get("agent")
        agent_id = str(raw_agent).strip() if raw_agent else None

        # Resolve agent_id via librarian if not directly supplied by action details
        if not agent_id:
            if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(
                self.librarian.resolve_agent_id_for_role
            ):
                agent_id = self.librarian.resolve_agent_id_for_role(role_name)
            elif hasattr(self.librarian, "resolve_agent_id") and callable(
                self.librarian.resolve_agent_id
            ):
                agent_id = self.librarian.resolve_agent_id(role_name)

        # Fail-fast assertion: synthetic string fallbacks (e.g., agent_id = role_name) are prohibited
        if not agent_id:
            raise RoleConfigurationError(
                f"[FATAL ESCALATION FAULT] Required system role '{role_name}' "
                f"is not mapped to an active agent in SkillLibrarian state."
            )

        return role_name, str(agent_id)

    def _evaluate_diagnostic_and_build_constraints(
        self, failure_reason: Union[str, Dict[str, Any], BaseModel]
    ) -> ConstraintRevision:
        """Ingests raw diagnostic outputs/artifacts and constructs a structured ConstraintRevision."""
        data: Dict[str, Any] = {}
        if isinstance(failure_reason, BaseModel):
            data = failure_reason.model_dump()
        elif isinstance(failure_reason, dict):
            data = failure_reason
        else:
            data = {"message": str(failure_reason)}

        forbidden = list(data.get("forbidden_actions", []))
        if data.get("failed_step") and data["failed_step"] not in forbidden:
            forbidden.append(str(data["failed_step"]))
        if data.get("failed_action") and data["failed_action"] not in forbidden:
            forbidden.append(str(data["failed_action"]))

        adaptations = list(data.get("required_adaptations", []))
        if data.get("suggested_fix"):
            adaptations.append(str(data["suggested_fix"]))
        if data.get("schema_errors"):
            adaptations.append(f"Correct schema violations: {data['schema_errors']}")

        summary = (
            data.get("message")
            or data.get("error_type")
            or data.get("gap_type")
            or str(failure_reason)
        )

        return ConstraintRevision(
            forbidden_actions=forbidden,
            required_adaptations=adaptations,
            failure_summary=summary,
            diagnostic_context=data,
        )

    def escalate(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        failure_reason: Union[str, Dict[str, Any], BaseModel],
    ) -> None:
        """Triggers Evaluation Contract, constraint injection, or direct L4 Engineer Fallback."""
        current_level = requirement.escalation_level
        failed_cap_name = requirement.capability_required

        # Preserve root failed capability on blackboard prior to rewriting requirement
        if not blackboard.has_artifact("failed_capability"):
            blackboard.set_artifact("failed_capability", failed_cap_name)

        # Ingest DiagnosticArtifact and generate ConstraintRevision
        constraint_revision = self._evaluate_diagnostic_and_build_constraints(failure_reason)

        # Track attempts for current agent/requirement
        params = requirement.parameters or {}
        attempt_count = params.get("_attempt_count", 0) + 1
        params["_attempt_count"] = attempt_count

        logger.warning(
            f"[Escalation] Failure detected on requirement '{failed_cap_name}' "
            f"(Attempt {attempt_count}/2 for current agent) at Level {getattr(current_level, 'value', current_level)}. "
            f"Reason: {constraint_revision.failure_summary}"
        )

        # -------------------------------------------------------------------------
        # SCENARIO A: Attempt 1 Failure -> Inject Constraints & Retry In-Place ("Final Chance")
        # -------------------------------------------------------------------------
        if attempt_count == 1 and current_level != EscalationLevel.L4_ENGINEER_FALLBACK:
            # Merge revision into payload parameters
            existing_forbidden = set(params.get("forbidden_actions", []))
            existing_forbidden.update(constraint_revision.forbidden_actions)
            params["forbidden_actions"] = list(existing_forbidden)

            existing_adaptations = set(params.get("required_adaptations", []))
            existing_adaptations.update(constraint_revision.required_adaptations)
            params["required_adaptations"] = list(existing_adaptations)

            params["constraint_revision"] = constraint_revision.model_dump()
            requirement.parameters = params

            logger.info(
                f"[Escalation] Injected dynamic ConstraintRevision into '{failed_cap_name}' payload. "
                f"Forbidden: {params['forbidden_actions']} | Adaptations: {params['required_adaptations']}"
            )

            blackboard.escalate(
                reason=f"In-place retry with injected constraints: {constraint_revision.failure_summary}"
            )

            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.ESCALATION,
                    agent_name="Coordinator",
                    action=failed_cap_name,
                    details={
                        "task_id": str(blackboard.task_id),
                        "level": getattr(current_level, "value", current_level),
                        "attempt": 1,
                        "retry_in_place": True,
                        "forbidden_actions": params["forbidden_actions"],
                        "required_adaptations": params["required_adaptations"],
                        "reason": constraint_revision.failure_summary,
                        "terminal": False,
                    },
                )
            )
            return

        # -------------------------------------------------------------------------
        # SCENARIO B: Attempt 2+ Failure or L3 Escalation -> Direct L4 Engineer Fallback
        # -------------------------------------------------------------------------
        if current_level != EscalationLevel.L4_ENGINEER_FALLBACK:
            logger.warning(
                f"[Escalation] Agent failed second attempt on requirement '{failed_cap_name}'. "
                "Escalating directly to L4_ENGINEER_FALLBACK."
            )

            action_name = "synthesize_script_fallback"
            l4_details = self.librarian.get_action_details(action_name) or {}
            role_name, agent_id = self._resolve_agent_target(l4_details, "system_engineer")

            new_level = EscalationLevel.L4_ENGINEER_FALLBACK
            new_cap = l4_details.get("capability_name", l4_details.get("action_name", action_name))

            # Preserve history & re-assign payload to Engineer
            diag_history = params.get("diagnostic_history", [])
            diag_history.append(constraint_revision.model_dump())

            requirement.escalation_level = new_level
            requirement.capability_required = new_cap
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

            requirement.parameters = {
                "prompt": params.get("prompt", f"Resolve failed capability: {failed_cap_name}"),
                "failed_capability": failed_cap_name,
                "diagnostic_history": diag_history,
                "last_diagnostic": constraint_revision.model_dump(),
                "_attempt_count": 0,  # Reset for Engineer
            }

            blackboard.escalate(
                reason=f"Escalating to Engineer Fallback following repeat agent failure: {constraint_revision.failure_summary}"
            )

            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.ESCALATION,
                    agent_name="Coordinator",
                    action=failed_cap_name,
                    details={
                        "task_id": str(blackboard.task_id),
                        "from_level": getattr(current_level, "value", current_level),
                        "to_level": getattr(new_level, "value", new_level),
                        "assigned_agent": agent_id,
                        "new_capability": new_cap,
                        "reason": constraint_revision.failure_summary,
                        "terminal": False,
                    },
                )
            )
            return

        # -------------------------------------------------------------------------
        # SCENARIO C: Level 4 Failure -> Unrecoverable Terminal Failure
        # -------------------------------------------------------------------------
        logger.critical(
            f"[Escalation] Task {blackboard.task_id} failed under Level 4 Engineer Fallback. Terminal state."
        )
        blackboard.status = TaskStatus.FAILED
        blackboard.unfulfilled_requirements.clear()

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.ESCALATION,
                agent_name="Coordinator",
                action=failed_cap_name,
                details={
                    "task_id": str(blackboard.task_id),
                    "from_level": getattr(current_level, "value", current_level),
                    "to_level": "TERMINAL_FAILURE",
                    "reason": constraint_revision.failure_summary,
                    "terminal": True,
                },
            )
        )