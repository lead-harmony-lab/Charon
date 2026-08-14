"""
charon/core/contracts.py
System Version: v2.0.0

Module: Core Execution Envelopes & Diagnostic Artifacts.
Provides strict Pydantic V2 schemas for execution outputs, root-cause diagnostics,
and declarative skill blueprints for the Charon system.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    """Status code returned by a role executor following a contract execution loop."""

    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    INCAPABLE = "INCAPABLE"
    FAILED = "FAILED"


class GapType(str, Enum):
    """Taxonomy of capability gaps identified during fast-fail execution (The Flashlight)."""

    ACTION_UNSUPPORTED = "ACTION_UNSUPPORTED"
    MISSING_ARTIFACT = "MISSING_ARTIFACT"
    MISSING_SYSTEM_DEPENDENCY = "MISSING_SYSTEM_DEPENDENCY"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"


class DiagnosticArtifact(BaseModel):
    """Structured root-cause diagnostic explaining exactly why a role failed its contract."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gap_type: GapType = Field(
        description="Categorical root-cause identifier for the execution barrier."
    )
    description: str = Field(
        description="Human/LLM readable detail of the missing capability, state, or schema violation."
    )
    missing_key_or_tool: Optional[str] = Field(
        default=None,
        description="Specific missing blackboard artifact key, binary executable, or tool constraint.",
    )
    suggested_remediation: str = Field(
        description="Actionable guidance for the EscalationManager (e.g., required constraints or missing prerequisites)."
    )


class SkillBlueprint(BaseModel):
    """Declarative specification generated when a role ad-hoc solves a recurring task."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    suggested_skill_name: str = Field(
        description="PascalCase name suggested for the new permanent Skill class."
    )
    action_name: str = Field(
        description="Snake_case string identifier for the action capability."
    )
    target_role: str = Field(
        description="Target specialist role persona best suited to adopt this skill."
    )
    description: str = Field(
        description="Summary of what the skill performs and when it should be invoked."
    )
    inputs_required: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys required as prerequisites.",
    )
    outputs_produced: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys produced upon successful execution.",
    )
    system_dependencies: List[str] = Field(
        default_factory=list,
        description="CLI tools or python packages required by the skill execution.",
    )
    adhoc_code_reference: Optional[str] = Field(
        default=None,
        description="File path or temp log ID where ad-hoc execution code was archived.",
    )


class ContractResponse(BaseModel):
    """Standardized execution boundary returned by the Work Contract to the Coordinator."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str = Field(
        description="Identity of the executing specialist role."
    )
    status: ExecutionStatus = Field(
        description="Outcome status of the execution envelope."
    )
    accomplishments: List[str] = Field(
        default_factory=list,
        description="Summary of work or sub-tasks successfully completed.",
    )
    unresolved_gaps: List[str] = Field(
        default_factory=list,
        description="Sub-tasks or constraints the role could NOT satisfy.",
    )
    diagnostics: Optional[DiagnosticArtifact] = Field(
        default=None,
        description="Flashlight diagnostic detailing specific root-cause if INCAPABLE or FAILED.",
    )
    skill_blueprint: Optional[SkillBlueprint] = Field(
        default=None,
        description="Optional blueprint emitted when ad-hoc problem solving successfully completes.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Detailed system diagnostic message or raw exception string.",
    )