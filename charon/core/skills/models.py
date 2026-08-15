"""
charon/core/skills/models.py
System Version: v2.0.0 | File Revision: 1.0.0

Module: Pydantic schemas for dynamic skill manifests and action specifications.
Enforces Pydantic V2 validation and V2 Declarative Action array schema.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

class ActionMetadata(BaseModel):
    """Schema defining individual action capability specs inside a skill."""

    action_name: str = Field(..., description="Unique action capability key.")
    handler_name: str = Field(
        ..., description="Target python function or Class name in plugin.py."
    )
    description: str = Field(
        default="", description="Human-readable summary of what the action does."
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for parameters."
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="CBAC Schema V2 permissions required to execute this action.",
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list, description="Expected input artifact types."
    )
    produced_artifacts: List[str] = Field(
        default_factory=list, description="Expected output artifact types."
    )

class SkillManifest(BaseModel):
    """Pydantic v2 schema governing dynamic disk-based skill plugin manifests (manifest.json)."""

    skill_id: str = Field(..., description="Unique skill identifier")
    version: str = Field(default="2.0.0", description="SemVer version string")
    skill_type: str = Field(default="tool", description="Type of skill: tool, work_contract, or system")
    description: str = Field(default="", description="Package-level skill description")
    category: str = Field(default="General", description="Taxonomy category")
    status: str = Field(default="ACTIVE", description="Lifecycle status (ACTIVE, QUARANTINED).")
    quarantine_reason: Optional[str] = Field(default=None)
    required_permissions: List[str] = Field(default_factory=list)
    author: str = Field(default="Charon Librarian")
    primary_agent_id: str = Field(default="system_generalist")
    allowed_agents: List[str] = Field(default_factory=list)
    shelf_tags: List[str] = Field(default_factory=list)

    # V2 Strict Actions Array
    actions: List[ActionMetadata] = Field(default_factory=list, description="List of discrete capabilities provided by this skill.")

    system_requirements: List[str] = Field(default_factory=list)

    @field_validator("primary_agent_id", mode="before")
    @classmethod
    def sanitize_primary_agent(cls, v: Any) -> str:
        if not v: return "system_generalist"
        return str(getattr(v, "value", v)).strip()

    @field_validator("allowed_agents", mode="before")
    @classmethod
    def sanitize_allowed_agents(cls, v: Any) -> List[str]:
        if isinstance(v, str): v = [v]
        if isinstance(v, list):
            return [str(getattr(a, "value", a)).strip() for a in v if a]
        return v