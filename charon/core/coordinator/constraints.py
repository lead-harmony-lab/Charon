"""
charon/core/coordinator/constraints.py
System Version: v1.0.0 | File Revision: 10.0.0

Module: Constraint Extraction and Diagnostic Evaluation.
Provides stateless helpers to ingest failure artifacts/diagnostics
and compile dynamic ConstraintRevisions for task re-planning.
"""

import logging
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field

logger = logging.getLogger("charon.core.coordinator.escalation")


class ConstraintRevision(BaseModel):
    """Dynamic constraints injected into task retry payloads or planner re-plans."""

    forbidden_actions: List[str] = Field(default_factory=list)
    required_adaptations: List[str] = Field(default_factory=list)
    failure_summary: str = ""
    diagnostic_context: Dict[str, Any] = Field(default_factory=dict)


def build_constraint_revision(
    failure_reason: Union[str, Dict[str, Any], BaseModel]
) -> ConstraintRevision:
    """Ingests raw diagnostic outputs or error artifacts and builds a structured ConstraintRevision."""
    data: Dict[str, Any] = {}
    if isinstance(failure_reason, BaseModel):
        data = failure_reason.model_dump()
    elif isinstance(failure_reason, dict):
        data = failure_reason
    else:
        data = {"message": str(failure_reason)}

    forbidden = list(data.get("forbidden_actions", []))
    if data.get("failed_step") is not None and str(data["failed_step"]) not in forbidden:
        forbidden.append(str(data["failed_step"]))
    if data.get("failed_action") and str(data["failed_action"]) not in forbidden:
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