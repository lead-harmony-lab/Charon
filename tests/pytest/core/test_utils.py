"""Unit tests for utility routines in charon.core.utils."""

import pytest

from charon.core.utils import clean_json_string, get_schema_json, normalize_agent
from charon.intent import AgentEnum


class TestCleanJsonString:
    """Tests for extracting and sanitizing JSON string payloads from LLM outputs."""

    def test_clean_raw_json_string_unmodified(self):
        raw = '{"name": "charon", "active": true}'
        assert clean_json_string(raw) == '{"name": "charon", "active": true}'

    def test_clean_markdown_fenced_json(self):
        raw = (
            "Here is the result:\n"
            "```json\n"
            "{\n"
            '    "key": "value",\n'
            '    "count": 42\n'
            "}\n"
            "```\n"
            "Hope this helps!"
        )
        expected = '{\n    "key": "value",\n    "count": 42\n}'
        assert clean_json_string(raw) == expected

    def test_clean_markdown_fenced_without_json_tag(self):
        raw = "```\n" '{"status": "ok"}\n' "```"
        assert clean_json_string(raw) == '{"status": "ok"}'

    def test_clean_unfenced_json_embedded_in_prose(self):
        raw = 'Sure, here is the payload: {"agent": "architect"} - let me know.'
        assert clean_json_string(raw) == '{"agent": "architect"}'

    def test_remove_trailing_commas_object_and_array(self):
        raw = '{"items": [1, 2, 3,], "nested": {"a": "b",},}'
        cleaned = clean_json_string(raw)
        assert cleaned == '{"items": [1, 2, 3], "nested": {"a": "b"}}'

    def test_whitespace_and_newlines_trimmed(self):
        raw = '  \n\n  {\n  "action": "ping"\n}  \n  '
        assert clean_json_string(raw) == '{\n  "action": "ping"\n}'

    def test_no_json_curly_braces_returns_stripped_input(self):
        raw = "   just standard plain text without json   "
        assert clean_json_string(raw) == "just standard plain text without json"


class TestNormalizeAgent:
    """Tests for coercing string inputs or existing AgentEnum instances into AgentEnum."""

    def test_normalize_with_existing_agent_enum_instance(self):
        agent = AgentEnum.ARCHITECT
        assert normalize_agent(agent) is AgentEnum.ARCHITECT

    def test_normalize_with_exact_value_string(self):
        result = normalize_agent("The_Architect")
        assert result == AgentEnum.ARCHITECT

    def test_normalize_with_enum_key_name(self):
        result = normalize_agent("ARCHITECT")
        assert result == AgentEnum.ARCHITECT

    def test_normalize_with_fuzzy_lowercase_string(self):
        result = normalize_agent("architect")
        assert result == AgentEnum.ARCHITECT

    def test_normalize_with_prefixed_lowercase_string(self):
        result = normalize_agent("the_architect")
        assert result == AgentEnum.ARCHITECT

    def test_normalize_with_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_agent("non_existent_agent")


class TestGetSchemaJson:
    """Tests for defensive extraction of JSON schemas from model classes."""

    def test_get_schema_json_via_custom_get_clean_schema(self):
        mock_schema = {"type": "object", "title": "CustomSchema"}

        class DummyModelWithCleanSchema:
            @classmethod
            def get_clean_schema(cls):
                return mock_schema

        assert get_schema_json(DummyModelWithCleanSchema) == mock_schema

    def test_get_schema_json_via_pydantic_v2_model_json_schema(self):
        mock_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        class DummyPydanticV2Model:
            @classmethod
            def model_json_schema(cls):
                return mock_schema

        assert get_schema_json(DummyPydanticV2Model) == mock_schema

    def test_get_clean_schema_takes_precedence_over_model_json_schema(self):
        custom_schema = {"source": "get_clean_schema"}
        v2_schema = {"source": "model_json_schema"}

        class DummyModelBothMethods:
            @classmethod
            def get_clean_schema(cls):
                return custom_schema

            @classmethod
            def model_json_schema(cls):
                return v2_schema

        assert get_schema_json(DummyModelBothMethods) == custom_schema

    def test_get_schema_json_fallback_returns_empty_dict(self):
        class PlainClassWithoutSchemaMethods:
            pass

        assert get_schema_json(PlainClassWithoutSchemaMethods) == {}

    def test_get_schema_json_ignores_non_callable_attributes(self):
        class DummyClassWithNonCallableAttributes:
            get_clean_schema = "not_a_callable"
            model_json_schema = {"not": "a_function"}

        assert get_schema_json(DummyClassWithNonCallableAttributes) == {}
