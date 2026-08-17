"""
System Version: v2.0.0 | File Revision: 2.0.0

Module: Pydantic schemas for dynamic skill manifests and action specifications.
Enforces Pydantic V2 validation and V2 Declarative Action array schema.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActionMetadata(BaseModel):
    """Schema defining individual action capability specs inside a skill."""

    skill_id: str = Field(
        ..., description="Unique skill identifier corresponding to the database record."
    )
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
    system_requirements: List[str] = Field(
        default_factory=list, description="Action-specific required binaries/dependencies."
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list, description="Expected input artifact types."
    )
    produced_artifacts: List[str] = Field(
        default_factory=list, description="Expected output artifact types."
    )


class SkillManifest(BaseModel):
    """Pydantic v2 schema governing dynamic disk-based skill plugin manifests (manifest.json)."""

    package: str = Field(..., description="Unique package namespace identifier on disk.")
    version: str = Field(default="2.0.0", description="SemVer version string")
    skill_type: str = Field(
        default="tool", description="Type of skill: tool, work_contract, or system"
    )
    description: str = Field(default="", description="Package-level skill description")
    category: str = Field(default="General", description="Taxonomy category")
    is_global: bool = Field(
        default=False, description="Whether skill capability is globally accessible."
    )
    status: str = Field(
        default="ACTIVE", description="Lifecycle status (ACTIVE, QUARANTINED)."
    )
    quarantine_reason: Optional[str] = Field(default=None)
    required_permissions: List[str] = Field(default_factory=list)
    author: str = Field(default="Charon Librarian")
    shelf_tags: List[str] = Field(default_factory=list)

    # Package-level fallbacks
    system_requirements: List[str] = Field(
        default_factory=list, description="Package-wide system binaries/dependencies."
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list, description="Package-wide fallback input artifact types."
    )
    produced_artifacts: List[str] = Field(
        default_factory=list, description="Package-wide fallback output artifact types."
    )

    # V2 Strict Actions Array
    actions: List[ActionMetadata] = Field(
        default_factory=list,
        description="List of discrete capabilities provided by this skill package.",
    )