"""
charon/intent/routing.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: First pass routing classification and unified intent extraction schemas.
"""

from typing import Any, Dict, Optional
from pydantic import Field
from charon.intent.base import StrictBaseModel


class RoutingPayload(StrictBaseModel):
    """
    First inference pass: Determine WHO should handle the task.
    Purely analytical classification. No conversational text generation allowed.
    """
    agent: str = Field(
        description="The exact agent_id (e.g., 'The_Engineer', 'The_Planner') assigned to execute the requested task. Must match an active agent in the system registry."
    )


class IntentExtraction(StrictBaseModel):
    """Unified intent extraction payload returned during orchestrator parsing."""

    agent: str = Field(
        description="The exact agent_id assigned to the task."
    )
    action: str = Field(
        description="The dynamic action_name to invoke."
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, description="Extraction confidence score (0.0 to 1.0).")
    raw_prompt: Optional[str] = Field(default=None, description="Original user prompt string.")
    requires_approval: bool = Field(
        default=False, description="Flag indicating if action requires human confirmation via Gatekeeper."
    )