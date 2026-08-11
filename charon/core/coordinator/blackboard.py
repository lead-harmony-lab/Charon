"""
charon/core/coordinator/blackboard.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Core state blackboard and execution TaskBlackboard models.
Provides strongly-typed schemas for multi-step artifact propagation, unfulfilled task tracking,
contract reflection, state mutation tracking, execution history, and DB state hydration.
Strictly preserves canonical database identifiers across all state interactions.
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import Field

from charon.core.contracts import ContractResponse, ExecutionStatus
from charon.core.skills.librarian import SkillLibrarian
from charon.intent.base import StrictBaseModel


class TaskStatus(str, Enum):
    """Lifecycle status of a TaskBlackboard."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_ESCALATION = "NEEDS_ESCALATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EscalationLevel(IntEnum):
    """The 4-Level Self-Healing Escalation Hierarchy."""

    L1_SPECIALIST = 1        # Domain specialist actions
    L2_OS_AUTOMATION = 2     # OS automation and shell operations
    L3_DIAGNOSTIC = 3        # Diagnostic planning & environment analysis
    L4_ENGINEER_FALLBACK = 4 # System engineer fallback & custom repair


class ThoughtType(str, Enum):
    """Categorizes the phase of internal role/coordinator reasoning."""

    ANALYSIS = "ANALYSIS"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    REFLECTION = "REFLECTION"
    ERROR = "ERROR"


class ThoughtRecord(StrictBaseModel):
    """Granular CoT reasoning step emitted by the Coordinator or Specialist Roles."""

    record_id: str = Field(
        default_factory=lambda: f"thg-{uuid.uuid4().hex[:6]}",
        description="Unique identifier for the reasoning record.",
    )
    task_id: str = Field(description="Associated blackboard task ID.")
    source_role: str = Field(description="Abstract role or module key emitting the thought.")
    thought_type: ThoughtType = Field(
        default=ThoughtType.ANALYSIS,
        description="Phase category of the reasoning step.",
    )
    message: str = Field(description="Internal CoT narrative payload.")
    context_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional telemetry payloads (e.g., partial tool inputs, query parameters).",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of thought emission.",
    )


class UnfulfilledRequirement(StrictBaseModel):
    """Represents a discrete goal or action that has not yet been satisfied."""

    requirement_id: str = Field(
        default_factory=lambda: f"req-{uuid.uuid4().hex[:6]}",
        description="Unique identifier for the requirement.",
    )
    capability_required: str = Field(
        description="The capability required to fulfill this step."
    )
    target_artifact_key: Optional[str] = Field(
        default=None,
        description="Key in the blackboard artifacts dictionary required for this step.",
    )
    preferred_tool: Optional[str] = Field(
        default=None,
        description="Optional preferred tool/app requested by the user.",
    )
    escalation_level: EscalationLevel = Field(
        default=EscalationLevel.L1_SPECIALIST,
        description="Current escalation level assigned to resolve this requirement.",
    )
    assigned_role_override: Optional[str] = Field(
        default=None,
        description="Abstract system role assigned during escalation (e.g., 'system_engineer').",
    )
    assigned_agent_override: Optional[str] = Field(
        default=None,
        description="Resolved agent_id matching agent_registry FK constraint.",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted target parameters bound to this specific requirement.",
    )


class ExecutionStepRecord(StrictBaseModel):
    """Audit log entry representing a single role execution turn."""

    step_number: int = Field(description="1-based index of the step execution order.")
    role: str = Field(description="The specialist role or agent_id that executed the step.")
    action: str = Field(description="The specific domain action invoked.")
    status: str = Field(
        default="SUCCESS",
        description="Outcome status of the step.",
    )
    output_summary: str = Field(
        default="",
        description="Human-readable or LLM-friendly summary of the output generated.",
    )
    produced_artifacts: Dict[str, Any] = Field(
        default_factory=dict,
        description="New artifacts added to the blackboard during this step.",
    )
    unresolved_gaps: List[str] = Field(
        default_factory=list,
        description="Sub-task requirements that could not be completed during this turn.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Detailed diagnostic error output if execution failed.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of execution.",
    )


class TaskBlackboard(StrictBaseModel):
    """The shared state blackboard for Charon execution turns."""

    task_id: str = Field(
        default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}",
        description="Unique execution session identifier.",
    )
    original_prompt: str = Field(
        description="Unmodified prompt string supplied by the user."
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current operational state of the blackboard.",
    )
    current_escalation_level: EscalationLevel = Field(
        default=EscalationLevel.L1_SPECIALIST,
        description="Highest active escalation level reached during execution.",
    )

    artifacts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ground truth key-value store containing operational data.",
    )
    unfulfilled_requirements: List[UnfulfilledRequirement] = Field(
        default_factory=list,
        description="Queue of unsatisfied intents that the Coordinator must satisfy.",
    )
    active_gaps: List[str] = Field(
        default_factory=list,
        description="Accumulated sub-task gaps that require re-routing or escalation.",
    )
    execution_history: List[ExecutionStepRecord] = Field(
        default_factory=list,
        description="Ordered list of execution records for auditing and reflection.",
    )
    thought_stream: List[ThoughtRecord] = Field(
        default_factory=list,
        description="Live chronological CoT reasoning events emitted during execution.",
    )
    mutation_ledger: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed audit log of state mutations.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="System runtime metadata.",
    )

    @property
    def available_artifact_keys(self) -> Set[str]:
        """Returns non-empty keys available in the current blackboard artifact store."""
        return {k for k, v in self.artifacts.items() if v is not None and v != ""}

    def get_role_display_name(self, role: str) -> str:
        """Resolves human-readable presentation label via SkillLibrarian accessors."""
        clean_role = str(getattr(role, "value", role)).strip() if role else ""
        if not clean_role:
            return "system_generalist"

        librarian = SkillLibrarian.get_instance()
        if hasattr(librarian, "get_display_name_for_role") and callable(
            librarian.get_display_name_for_role
        ):
            name = librarian.get_display_name_for_role(clean_role)
            if name:
                return name
        if hasattr(librarian, "get_display_name_for_agent") and callable(
            librarian.get_display_name_for_agent
        ):
            name = librarian.get_display_name_for_agent(clean_role)
            if name:
                return name
        return clean_role

    def emit_thought(
        self,
        source_role: str,
        message: str,
        thought_type: ThoughtType = ThoughtType.ANALYSIS,
        context_data: Optional[Dict[str, Any]] = None,
        bus_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ThoughtRecord:
        """Emits a live CoT reasoning event to the blackboard and optional bus callback."""
        clean_role = (
            str(getattr(source_role, "value", source_role)).strip()
            if source_role
            else "system_generalist"
        )
        record = ThoughtRecord(
            task_id=self.task_id,
            source_role=clean_role,
            thought_type=thought_type,
            message=message,
            context_data=context_data or {},
        )
        self.thought_stream.append(record)

        if bus_callback and callable(bus_callback):
            try:
                bus_callback(record.model_dump())
            except Exception:
                pass

        return record

    def _safe_summary(self, value: Any, max_len: int = 250) -> str:
        """Safely summarizes ledger values to prevent memory bloat with large artifacts."""
        if value is None:
            return "None"
        try:
            val_str = str(value)
            if len(val_str) > max_len:
                return f"{val_str[:max_len]}... [Truncated {len(val_str) - max_len} chars]"
            return val_str
        except Exception:
            return f"<{type(value).__name__} Unserializable Object>"

    def set_artifact(self, key: str, value: Any, source_role: str = "system_generalist") -> None:
        """Stores a ground truth artifact on the blackboard and logs a truncated mutation."""
        clean_role = (
            str(getattr(source_role, "value", source_role)).strip()
            if source_role
            else "system_generalist"
        )
        previous_val = self.artifacts.get(key)
        self.artifacts[key] = value

        self.mutation_ledger.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "key": key,
            "previous_value": self._safe_summary(previous_val),
            "new_value": self._safe_summary(value),
            "source_role": clean_role,
        })

    def get_artifact(self, key: str, default: Any = None) -> Any:
        """Retrieves a ground truth artifact from the blackboard."""
        return self.artifacts.get(key, default)

    def has_artifact(self, key: str) -> bool:
        """Checks if a ground truth artifact exists and is non-empty."""
        val = self.artifacts.get(key)
        return val is not None and val != ""

    def log_gap(self, gap_description: str) -> None:
        """Logs an unresolved step gap for the Coordinator's reflection loop."""
        if gap_description and gap_description not in self.active_gaps:
            self.active_gaps.append(gap_description)

    def clear_gap(self, gap_description: str) -> None:
        """Removes a resolved gap from the active gaps list."""
        if gap_description in self.active_gaps:
            self.active_gaps.remove(gap_description)

    def record_step(
        self,
        role: Any = None,
        action: str = "",
        status: str = "SUCCESS",
        output_summary: str = "",
        produced_artifacts: Optional[Dict[str, Any]] = None,
        unresolved_gaps: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        agent: Any = None,  # Alias for role
    ) -> ExecutionStepRecord:
        """Appends an execution turn to history and updates blackboard artifacts."""
        resolved_role = role if role is not None else agent
        clean_role = (
            str(getattr(resolved_role, "value", resolved_role)).strip()
            if resolved_role
            else "system_generalist"
        )

        produced = produced_artifacts or {}
        gaps = unresolved_gaps or []
        step_number = len(self.execution_history) + 1

        record = ExecutionStepRecord(
            step_number=step_number,
            role=clean_role,
            action=action,
            status=status,
            output_summary=output_summary,
            produced_artifacts=produced,
            unresolved_gaps=gaps,
            error_message=error_message,
        )
        self.execution_history.append(record)

        for gap in gaps:
            self.log_gap(gap)

        for k, v in produced.items():
            self.set_artifact(k, v, source_role=clean_role)

        return record

    def record_contract_response(
        self,
        response: ContractResponse,
        action: str,
        produced_artifacts_map: Optional[Dict[str, Any]] = None,
    ) -> ExecutionStepRecord:
        """Integrates a formal Pydantic ContractResponse directly into state history."""
        produced = produced_artifacts_map or {}
        summary = (
            " | ".join(response.accomplishments)
            if response.accomplishments
            else (response.reason or "")
        )

        resolved_role = getattr(
            response,
            "role_name",
            getattr(response, "agent_name", "system_generalist"),
        )

        is_success = response.status in (ExecutionStatus.SUCCESS, ExecutionStatus.SATISFIED)

        return self.record_step(
            role=resolved_role,
            action=action,
            status=response.status.value,
            output_summary=summary,
            produced_artifacts=produced,
            unresolved_gaps=response.unresolved_gaps,
            error_message=None if is_success else response.reason,
        )

    def pop_requirement(self, requirement_id: str) -> Optional[UnfulfilledRequirement]:
        """Removes and returns a fulfilled requirement from the queue."""
        for idx, req in enumerate(self.unfulfilled_requirements):
            if req.requirement_id == requirement_id:
                return self.unfulfilled_requirements.pop(idx)
        return None

    def escalate(self, reason: str) -> EscalationLevel:
        """Escalates the task level up to Level 4."""
        if self.current_escalation_level < EscalationLevel.L4_ENGINEER_FALLBACK:
            self.current_escalation_level = EscalationLevel(
                self.current_escalation_level.value + 1
            )
            self.status = TaskStatus.NEEDS_ESCALATION
        else:
            self.status = TaskStatus.FAILED

        self.log_gap(f"Escalated to Level {self.current_escalation_level.value}: {reason}")
        return self.current_escalation_level

    def mark_completed(self) -> None:
        """Marks the blackboard state as fully satisfied."""
        self.status = TaskStatus.COMPLETED
        self.unfulfilled_requirements.clear()
        self.active_gaps.clear()

    def to_task_state_record(self) -> Dict[str, Any]:
        """Serializes blackboard into SQLite `task_state` schema representation."""
        override_agent = None
        if self.unfulfilled_requirements:
            override_agent = self.unfulfilled_requirements[0].assigned_agent_override

        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "escalation_level": int(self.current_escalation_level),
            "assigned_agent_override": override_agent,
            "plan_json": json.dumps([req.model_dump() for req in self.unfulfilled_requirements]),
            "results_json": json.dumps({
                "artifacts": self.artifacts,
                "history": [rec.model_dump() for rec in self.execution_history],
                "active_gaps": self.active_gaps,
            }),
            "metadata_json": json.dumps(self.metadata),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }