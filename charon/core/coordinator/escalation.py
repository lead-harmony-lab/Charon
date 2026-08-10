"""
charon/core/coordinator/escalation.py
System Version: v0.4.1 | File Revision: 2.0.0

Module: 4-Level Self-Healing Escalation Engine.
Manages automatic step recovery with live TelemetryBus trace emissions,
strict DB role-to-agent resolution via SkillLibrarian, and fail-fast
assertions when system roles or default agents are unassigned.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.skills import SkillLibrarian
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator.escalation")


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role or default agent is not assigned in SQLite state."""


class EscalationManager:
    """Manages system failure escalations and updates task blackboards with fail-fast assertions."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_target(
        self, details: Dict[str, Any], default_system_role: str
    ) -> Tuple[str, str]:
        """
        Resolves (role_name, agent_id) from action details or system_roles lookup.
        Fails fast if the role or agent cannot be resolved from database state.
        """
        raw_role = details.get("primary_role_id") or details.get("role") or default_system_role
        raw_agent = details.get("primary_agent_id") or details.get("agent")

        role_name = str(raw_role)
        agent_id = str(raw_agent) if raw_agent else None

        # Resolve agent_id via librarian if not directly supplied by action details
        if not agent_id:
            try:
                if hasattr(self.librarian, "resolve_agent_id_for_role"):
                    agent_id = self.librarian.resolve_agent_id_for_role(role_name)
                elif hasattr(self.librarian, "resolve_role"):
                    agent_id = self.librarian.resolve_role(role_name)
                elif hasattr(self.librarian, "get_agent_for_role"):
                    agent_id = self.librarian.get_agent_for_role(role_name)
            except Exception as e:
                logger.error(
                    f"[Escalation] Critical error resolving role '{role_name}' via librarian: {e}"
                )
                agent_id = None

        # Fail-fast assertion: synthetic string fallbacks are prohibited
        if not agent_id:
            raise RoleConfigurationError(
                f"[FATAL ESCALATION FAULT] Required system role '{role_name}' "
                f"is not mapped to an active agent in 'system_roles' or 'agent_registry'."
            )

        return role_name, str(agent_id)

    def escalate(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        failure_reason: str,
    ) -> None:
        """Triggers the 4-Level Self-Healing Escalation Pathway and emits telemetry events."""
        current_level = requirement.escalation_level
        failed_cap_name = requirement.capability_required

        # Preserve root failed capability on blackboard prior to rewriting requirement
        if not blackboard.has_artifact("failed_capability"):
            blackboard.set_artifact("failed_capability", failed_cap_name)

        logger.warning(
            f"[Escalation] Escalating requirement '{failed_cap_name}' "
            f"from Level {current_level.value if hasattr(current_level, 'value') else current_level} "
            f"(Reason: {failure_reason})"
        )

        if current_level == EscalationLevel.L1_SPECIALIST:
            action_name = "execute_system_command"
            l2_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L2_OS_AUTOMATION
            new_cap = l2_details.get("capability_name", l2_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l2_details, "system_generalist")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        elif current_level == EscalationLevel.L2_OS_AUTOMATION:
            action_name = "diagnose_environment"
            l3_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L3_DIAGNOSTIC
            new_cap = l3_details.get("capability_name", l3_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l3_details, "system_engineer")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        elif current_level == EscalationLevel.L3_DIAGNOSTIC:
            action_name = "synthesize_script_fallback"
            l4_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L4_ENGINEER_FALLBACK
            new_cap = l4_details.get("capability_name", l4_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l4_details, "system_engineer")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        else:
            logger.critical(
                f"[Escalation] Task {blackboard.task_id} reached Level 4 Escalation failure. Terminal state."
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
                        "reason": failure_reason,
                        "terminal": True,
                    },
                )
            )
            return

        requirement.escalation_level = new_level
        requirement.capability_required = new_cap
        blackboard.escalate(reason=failure_reason)

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.ESCALATION,
                agent_name="Coordinator",
                action=failed_cap_name,
                details={
                    "task_id": str(blackboard.task_id),
                    "from_level": getattr(current_level, "value", current_level),
                    "to_level": getattr(new_level, "value", new_level),
                    "new_capability": new_cap,
                    "reason": failure_reason,
                    "terminal": False,
                },
            )
        )