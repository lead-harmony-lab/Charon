"""
charon/intent/base.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Foundational Pydantic models and schema helpers.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model enforcing robust parsing against local LLM output variations."""
    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=False,
        populate_by_name=True,
    )


class MemoryCandidate(StrictBaseModel):
    is_persistent: bool = Field(
        default=True,
        description="True if this constitutes a permanent rule, preference, or systemic fact.",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence level of the memory extraction (0.0 to 1.0).",
    )
    fact: str = Field(
        description="The exact preference, rule, or systemic fact to commit to the ledger."
    )


class BaseAgentPayload(StrictBaseModel):
    """Base payload allowing agents to passively capture systemic memories/preferences."""
    memory_candidate: Optional[MemoryCandidate] = Field(
        default=None,
        description="Optional preference/rule extracted during normal execution.",
    )

    @classmethod
    def get_clean_schema(cls) -> Dict[str, Any]:
        """Returns JSON schema with $defs inlined for Ollama structured outputs compatibility."""
        schema = cls.model_json_schema()
        defs = schema.pop("$defs", {})

        def resolve_refs(obj: Any) -> Any:
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            return resolve_refs(defs[def_name])
                return {k: resolve_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_refs(item) for item in obj]
            return obj

        return resolve_refs(schema)