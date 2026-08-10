from typing import Any, Dict
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from charon.intent.base import (
    AgentEnum,
    BaseAgentPayload,
    MemoryCandidate,
    StrictBaseModel,
)


class TestAgentEnum:
    """Tests for AgentEnum member definitions and values."""

    def test_agent_enum_values(self) -> None:
        """Verify enum members map to expected string values."""
        assert AgentEnum.SPARK == "The_Spark"
        assert AgentEnum.MACHINIST == "The_Machinist"
        assert AgentEnum.QUARTERMASTER == "The_Quartermaster"
        assert AgentEnum.CLEANER == "The_Cleaner"
        assert AgentEnum.PLANNER == "The_Planner"
        assert AgentEnum.ARCHIVIST == "The_Archivist"
        assert AgentEnum.GENERALIST == "The_Generalist"
        assert AgentEnum.ARCHITECT == "The_Architect"
        assert AgentEnum.SCOUT == "The_Scout"
        assert AgentEnum.ENGINEER == "The_Engineer"
        assert AgentEnum.OVERSEER == "The_Overseer"
        assert AgentEnum.STEWARD == "The_Steward"

    def test_agent_enum_count(self) -> None:
        """Verify the total count of defined agents."""
        assert len(AgentEnum) == 12


class TestStrictBaseModel:
    """Tests for StrictBaseModel configuration rules."""

    def test_extra_fields_ignored(self) -> None:
        """Verify extra unexpected payload fields are ignored without raising errors."""

        class DummyModel(StrictBaseModel):
            name: str

        instance = DummyModel.model_validate({"name": "test_agent", "extra_field": "ignore_me"})
        assert instance.name == "test_agent"
        assert not hasattr(instance, "extra_field")

    def test_populate_by_name_enabled(self) -> None:
        """Verify field population works using property names."""

        class DummyModel(StrictBaseModel):
            field_name: str

        instance = DummyModel.model_validate({"field_name": "value"})
        assert instance.field_name == "value"


class TestMemoryCandidate:
    """Tests for MemoryCandidate fields and default values."""

    def test_memory_candidate_defaults(self) -> None:
        """Verify default values when providing only required fields."""
        candidate = MemoryCandidate(fact="User prefers tabs over spaces")
        assert candidate.fact == "User prefers tabs over spaces"
        assert candidate.is_persistent is True
        assert candidate.confidence == 1.0

    def test_memory_candidate_custom_values(self) -> None:
        """Verify custom values override defaults correctly."""
        candidate = MemoryCandidate(
            fact="Temporary build directory override",
            is_persistent=False,
            confidence=0.75,
        )
        assert candidate.fact == "Temporary build directory override"
        assert candidate.is_persistent is False
        assert candidate.confidence == 0.75

    def test_memory_candidate_requires_fact(self) -> None:
        """Verify validation error is raised if 'fact' is missing."""
        with pytest.raises(ValidationError):
            MemoryCandidate()  # type: ignore


class TestBaseAgentPayload:
    """Tests for BaseAgentPayload structure and schema cleaning utilities."""

    def test_payload_defaults(self) -> None:
        """Verify memory_candidate defaults to None."""
        payload = BaseAgentPayload()
        assert payload.memory_candidate is None

    def test_payload_with_nested_memory_candidate(self) -> None:
        """Verify nested MemoryCandidate can be attached to payload."""
        candidate = MemoryCandidate(fact="Always set log level to DEBUG")
        payload = BaseAgentPayload(memory_candidate=candidate)
        assert payload.memory_candidate is not None
        assert payload.memory_candidate.fact == "Always set log level to DEBUG"

    def test_get_clean_schema_removes_defs(self) -> None:
        """Verify get_clean_schema strips $defs key from the generated schema."""
        raw_schema = BaseAgentPayload.model_json_schema()
        assert "$defs" in raw_schema  # Pydantic natively adds $defs for referenced models

        clean_schema = BaseAgentPayload.get_clean_schema()
        assert "$defs" not in clean_schema
        assert "properties" in clean_schema

    def test_get_clean_schema_handles_missing_defs(self) -> None:
        """Verify get_clean_schema executes safely when $defs is absent."""
        mock_schema: Dict[str, Any] = {
            "title": "BaseAgentPayload",
            "type": "object",
            "properties": {},
        }
        with patch.object(BaseAgentPayload, "model_json_schema", return_value=mock_schema):
            clean_schema = BaseAgentPayload.get_clean_schema()
            assert "$defs" not in clean_schema
            assert clean_schema == mock_schema
