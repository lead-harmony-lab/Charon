"""
charon/gateway/models.py
System Version: v0.1.0 | File Revision: 2.1.1

Module: Gateway REST request/response and WebSocket event schemas.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# Task & Intercept REST Models
# ==============================================================================

class TaskRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="Natural language prompt or command for Charon orchestration."
    )
    client_id: Optional[str] = Field(
        default="desktop_concierge",
        description="Originating client identifier."
    )
    agent_override: Optional[str] = Field(
        default=None,
        description="Optional agent key to bypass triage routing and force execution."
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Metadata or environmental context payload."
    )


class TaskResponse(BaseModel):
    task_id: str = Field(
        ...,
        description="Unique identifier assigned to the task."
    )
    status: Literal[
        "queued",
        "executing",
        "completed",
        "intercepted",
        "rescinded",
        "cancelled",
        "failed",
    ] = Field(
        ...,
        description="Current execution state of the task."
    )
    assigned_agent: Optional[str] = Field(
        default=None,
        description="The agent routed or assigned to handle this task."
    )
    message: str = Field(
        ...,
        description="Status summary, acknowledgment, or confirmation message."
    )
    result: Optional[Any] = Field(
        default=None,
        description="Execution output or structured payload if synchronously completed."
    )


class GatekeeperDecision(BaseModel):
    approval_id: str = Field(
        ...,
        description="Approval identifier matching the pre-flight intercept manifest."
    )
    decision: Literal["proceed", "rescind", "cancel"] = Field(
        ...,
        description="Physical authorization command submitted by the operator."
    )
    client_id: Optional[str] = Field(
        default="desktop_concierge",
        description="Identifier of the client node submitting the decision."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operator context or reasoning for the authorization response."
    )


# ==============================================================================
# Dynamic Router & Agent Control Models
# ==============================================================================

class AgentManifestResponse(BaseModel):
    """Payload representing an agent's dynamic routing configuration and capabilities."""
    agent_id: str = Field(..., description="Unique slug or key identifying the agent (e.g. 'the_machinist').")
    name: str = Field(..., description="Display name of the agent.")
    description: str = Field(..., description="Capability description evaluated during Pass 1 LLM triage.")
    system_prompt: str = Field(..., description="Base instructions injected into agent execution contexts.")
    priority_weight: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Multiplier applied to Pass 1 LLM confidence scores (0.1 to 5.0)."
    )
    override_triggers: List[str] = Field(
        default_factory=list,
        description="Keyword or prefix shortcuts that instantly bypass triage and force dispatch."
    )
    active_tools: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of registered tool schemas assigned to this agent."
    )
    status: Literal["active", "disabled", "maintenance"] = Field(
        default="active",
        description="Operational status of the agent node."
    )


class AgentUpdateRequest(BaseModel):
    """Request payload for mutating agent triage parameters at runtime."""
    description: Optional[str] = Field(
        default=None,
        description="Updated capability description fed into Pass 1 triage prompts."
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Updated system prompt for specialized execution."
    )
    priority_weight: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=5.0,
        description="Updated score multiplier for triage ranking."
    )
    override_triggers: Optional[List[str]] = Field(
        default=None,
        description="Updated list of exact keyword/prefix triggers forcing routing."
    )


class ToolPatchRequest(BaseModel):
    """Payload for dynamically toggling tool availability for an agent."""
    tool_name: str = Field(..., description="Exact class or module name of the targeted skill tool.")
    enabled: bool = Field(..., description="Target status for enabling or disabling tool execution.")


class DynamicRuleRequest(BaseModel):
    """Payload for defining hard-shortcut override routing rules."""
    trigger: str = Field(..., description="Exact trigger string or prefix (e.g., '#archivist', 'git:').")
    agent_id: str = Field(..., description="ID of the target agent to receive forced dispatch.")
    description: Optional[str] = Field(default="", description="Operator notes explaining rule purpose.")


class DynamicRuleResponse(BaseModel):
    """Outbound representation of an active dynamic shortcut rule."""
    rule_id: str = Field(..., description="Unique UUID assigned to the dynamic shortcut rule.")
    trigger: str = Field(..., description="Trigger string or prefix pattern.")
    target_agent: str = Field(..., description="Target agent ID handling the shortcut.")
    description: str = Field(default="", description="Rule operator notes.")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC creation timestamp."
    )


class TriageLogEntry(BaseModel):
    """Snapshot of a Pass 1 LLM triage evaluation for debugging and telemetry."""
    task_id: str = Field(..., description="Task identifier evaluated by triage.")
    prompt: str = Field(..., description="Original user prompt evaluated.")
    selected_agent: str = Field(..., description="Agent designated for dispatch.")
    confidence_score: float = Field(..., description="Final calculated confidence score after priority scaling.")
    candidate_scores: Dict[str, float] = Field(..., description="Raw or weighted score map across all candidates.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of evaluation."
    )


# ==============================================================================
# WebSocket Event Stream Models
# ==============================================================================

class WSEvent(BaseModel):
    event_type: Literal[
        "status_change",
        "agent_log",
        "agent_action",
        "agent_response",
        "thought_record",
        "telemetry_trace",
        "step",
        "task_progress",
        "gatekeeper_intercept",
        "concierge_suggestion",
        "task_complete",
        "overseer_report",
        "steward_event",
        "system_alert",
        "heartbeat_idle",
        "heartbeat_active",
        "router_agent_updated",
        "router_tool_toggled",
        "router_rule_changed",
        "error",
        "task_error",
        "gateway_ready",
    ] = Field(
        ...,
        description="Event discriminator consumed by desktop shell extensions or UI clients."
    )
    task_id: Optional[str] = Field(
        default=None,
        description="Active task identifier associated with the event, if applicable."
    )
    client_id: Optional[str] = Field(
        default=None,
        description="Target or origin client node identifier for network routing."
    )

    agent_name: str = Field(
        default="System",
        description="The specific agent emitting this event (e.g. 'The_Machinist', 'System')."
    )

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp generated at event emission."
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload containing telemetry, logs, or intercept parameters."
    )