"""
charon/core/skills/models.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Pydantic schemas for dynamic skill manifests and action specifications.
Enforces Pydantic V2 validation and schema normalization for SkillManifest and ActionMetadata.
Integrates CBAC Schema V2 permission declarations and quarantine lifecycle states.
Preserves raw identifier fidelity without forced case conversions or prefix mutations.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ActionMetadata(BaseModel):
    """Schema defining individual action capability specs inside a skill."""

    action_name: str = Field(..., description="Unique action capability key.")
    description: str = Field(
        default="", description="Human-readable summary of what the action does."
    )
    handler_name: str = Field(
        default="execute_action", description="Target python function name in plugin.py."
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

    skill_id: str = Field(..., description="Unique skill identifier, e.g. 'kicad_autoroute'")
    version: str = Field(default="1.0.0", description="SemVer version string for skill versioning")
    description: str = Field(default="", description="Package-level skill description")
    category: str = Field(default="General", description="Taxonomy category for skill organization")
    status: str = Field(
        default="ACTIVE",
        description="Lifecycle status of skill (ACTIVE, QUARANTINED, INACTIVE).",
    )
    quarantine_reason: Optional[str] = Field(
        default=None,
        description="Detailed explanation if skill is currently QUARANTINED.",
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="CBAC Schema V2 system permissions required by this skill.",
    )
    author: str = Field(default="Charon Librarian", description="Author or maintainer name")
    primary_agent_id: str = Field(
        default="system_generalist",
        description="Primary system role owner or canonical agent identifier",
    )
    allowed_agents: List[str] = Field(
        default_factory=list,
        description="Explicit list of agent_ids permitted to execute this skill. Empty grants zero permissions.",
    )
    shelf_tags: List[str] = Field(
        default_factory=list,
        description="Search and discovery keywords or categories for skill taxonomy",
    )
    supported_actions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of action capability keys to action definitions or handler strings",
    )
    action_descriptions: Dict[str, str] = Field(
        default_factory=dict,
        description="Action capability descriptions for semantic routing and LLM tool prompts",
    )
    action_parameters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="JSON Schema dictionary for each supported action capability",
    )
    system_requirements: List[str] = Field(
        default_factory=list,
        description="CLI binaries or system utilities required prior to execution",
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list,
        description="Input artifact types or extensions expected by this skill",
    )
    produced_artifacts: List[str] = Field(
        default_factory=list,
        description="Output artifact types or extensions produced by this skill",
    )

    @classmethod
    def get_clean_schema(cls) -> Dict[str, Any]:
        """Provides defensive schema export for core utils extraction compatibility."""
        return cls.model_json_schema()

    @staticmethod
    def _clean_identifier(role_str: Any) -> str:
        """Trims whitespace and extracts string value without case mutation or forced prefixes."""
        if not role_str:
            return ""
        return str(getattr(role_str, "value", role_str)).strip()

    @field_validator("primary_agent_id", mode="before")
    @classmethod
    def sanitize_primary_agent(cls, v: Any) -> str:
        """Sanitizes primary_agent_id into clean trimmed format."""
        cleaned = cls._clean_identifier(v)
        return cleaned or "system_generalist"

    @field_validator("allowed_agents", mode="before")
    @classmethod
    def sanitize_allowed_agents(cls, v: Any) -> List[str]:
        """Coerces strings/lists into trimmed agent identifier list format."""
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            res = []
            for agent in v:
                cleaned = cls._clean_identifier(agent)
                if cleaned:
                    res.append(cleaned)
            return res
        return v

    @field_validator("required_permissions", mode="before")
    @classmethod
    def coerce_string_to_list(cls, v: Any) -> Any:
        """Coerces single string entries into a standard list prior to schema validation."""
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_manifest_structure(cls, data: Any) -> Any:
        """
        Normalizes template nested action objects and legacy manifest structures.
        """
        if not isinstance(data, dict):
            return data

        # 1. Alias legacy 'actions' key -> 'supported_actions'
        if "actions" in data and "supported_actions" not in data:
            data["supported_actions"] = data.pop("actions")

        raw_actions = data.get("supported_actions", {})
        descriptions = data.setdefault("action_descriptions", {})
        parameters = data.setdefault("action_parameters", {})

        # 2. Parse Template Format: {"action_name": {"description": "...", "parameters": {...}}}
        if isinstance(raw_actions, dict):
            normalized_supported: Dict[str, Any] = {}
            for act_name, act_val in raw_actions.items():
                if isinstance(act_val, dict):
                    if "description" in act_val and act_name not in descriptions:
                        descriptions[act_name] = act_val["description"]
                    if "parameters" in act_val and act_name not in parameters:
                        parameters[act_name] = act_val.get("parameters", {})
                    handler = (
                        act_val.get("handler")
                        or act_val.get("handler_name")
                        or f"handle_{act_name}"
                    )
                    normalized_supported[act_name] = handler
                elif isinstance(act_val, str):
                    normalized_supported[act_name] = act_val

            data["supported_actions"] = normalized_supported

        # 3. Handle legacy list format: ['action1'] -> {'action1': 'handle_action1'}
        elif isinstance(raw_actions, list):
            data["supported_actions"] = {
                act: f"handle_{act}" for act in raw_actions if isinstance(act, str)
            }

        if "category" not in data or not data["category"]:
            data["category"] = "General"

        return data