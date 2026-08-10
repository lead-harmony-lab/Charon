import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from charon.core.parser import DEFAULT_ACTION_MAP, SCHEMA_MAP, IntentParser
from charon.intent import (
    AgentEnum,
    EngineerPayload,
    GeneralistPayload,
    PlannerPayload,
    RoutingPayload,
)


@pytest.fixture
def mock_ollama_client():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.get_context_string.return_value = ""
    return memory


@pytest.fixture
def parser(mock_ollama_client, mock_memory):
    return IntentParser(
        ollama_client=mock_ollama_client,
        triage_model="triage-model",
        heavy_model="heavy-model",
        memory=mock_memory,
    )


@pytest.mark.asyncio
class TestParseRouting:
    async def test_parse_routing_success(self, parser, mock_ollama_client):
        mock_ollama_client.generate.return_value = {
            "response": '{"agent": "The_Architect"}'
        }

        result = await parser.parse_routing("Create system architecture")

        assert isinstance(result, RoutingPayload)
        assert result.agent == AgentEnum.ARCHITECT
        mock_ollama_client.generate.assert_called_once()

    async def test_parse_routing_with_memory_context(
            self, parser, mock_ollama_client, mock_memory
    ):
        mock_memory.get_context_string.return_value = "User: Hello\nCharon: Greetings"
        mock_ollama_client.generate.return_value = {
            "response": '{"agent": "The_Generalist"}'
        }

        result = await parser.parse_routing("What can you do?")

        assert result.agent == AgentEnum.GENERALIST
        call_kwargs = mock_ollama_client.generate.call_args.kwargs
        assert "Recent Conversational Context:" in call_kwargs["prompt"]
        assert "User: Hello" in call_kwargs["prompt"]

    async def test_parse_routing_with_rejected_agents(self, parser, mock_ollama_client):
        mock_ollama_client.generate.return_value = {
            "response": '{"agent": "The_Planner"}'
        }

        result = await parser.parse_routing(
            "Plan a sprint", rejected_agents=["The_Architect", AgentEnum.ENGINEER]
        )

        assert result.agent == AgentEnum.PLANNER
        call_kwargs = mock_ollama_client.generate.call_args.kwargs
        assert "CRITICAL CONSTRAINT" in call_kwargs["prompt"]
        assert "The_Architect" in call_kwargs["prompt"]
        assert "The_Engineer" in call_kwargs["prompt"]

    async def test_parse_routing_failure_fallback_to_generalist(
            self, parser, mock_ollama_client
    ):
        mock_ollama_client.generate.side_effect = Exception("Ollama connection error")

        result = await parser.parse_routing("Hello charon")

        assert isinstance(result, RoutingPayload)
        assert result.agent == AgentEnum.GENERALIST


@pytest.mark.asyncio
class TestParseExtraction:
    async def test_parse_extraction_success(self, parser, mock_ollama_client):
        mock_ollama_client.generate.return_value = {
            "response": json.dumps({"action": "answer_query", "prompt": "What is Python?"})
        }

        result = await parser.parse_extraction(
            user_input="What is Python?", agent="GENERALIST"
        )

        assert isinstance(result, GeneralistPayload)
        assert result.prompt == "What is Python?"

    async def test_parse_extraction_prompt_enrichment_for_planner(
            self, parser, mock_ollama_client
    ):
        mock_ollama_client.generate.return_value = {
            "response": json.dumps(
                {"action": "draft_build_sequence", "prompt": "Build feature X"}
            )
        }
        ledger_context = "Ledger records retrieved:\n- Rule 1: Use TypeScript"

        result = await parser.parse_extraction(
            user_input="Build feature X",
            agent=AgentEnum.PLANNER,
            ledger_context=ledger_context,
        )

        assert isinstance(result, PlannerPayload)
        assert "PRIMARY USER COMMAND" in result.prompt
        assert "[SYSTEM LEDGER RULES & COMPLIANCE REQUIREMENTS]:" in result.prompt

    async def test_parse_extraction_prompt_enrichment_for_engineer(
            self, parser, mock_ollama_client
    ):
        mock_ollama_client.generate.return_value = {
            "response": json.dumps(
                {"action": "solve_coding_task", "problem": "Fix async bug"}
            )
        }
        ledger_context = "Ledger records retrieved:\n- Standard: Use asyncio"

        result = await parser.parse_extraction(
            user_input="Fix async bug",
            agent=AgentEnum.ENGINEER,
            ledger_context=ledger_context,
        )

        assert isinstance(result, EngineerPayload)
        assert "PRIMARY USER COMMAND" in result.problem
        assert "[SYSTEM LEDGER RULES & COMPLIANCE REQUIREMENTS]:" in result.problem

    async def test_parse_extraction_planner_without_ledger_records(
            self, parser, mock_ollama_client
    ):
        """Covers the 174->186 branch: Planner/Engineer agent WITHOUT matching ledger context."""
        mock_ollama_client.generate.return_value = {
            "response": json.dumps(
                {"action": "draft_build_sequence", "prompt": "Build feature Y"}
            )
        }

        result = await parser.parse_extraction(
            user_input="Build feature Y",
            agent=AgentEnum.PLANNER,
            ledger_context="No records here.",
        )

        assert isinstance(result, PlannerPayload)
        assert result.prompt == "Build feature Y"
        assert "PRIMARY USER COMMAND" not in result.prompt

    async def test_parse_extraction_fallback_on_exception(
            self, parser, mock_ollama_client
    ):
        mock_ollama_client.generate.side_effect = Exception("Invalid response format")

        result = await parser.parse_extraction(
            user_input="Search web", agent=AgentEnum.SCOUT
        )

        assert result is not None
        assert getattr(result, "query", None) == "Search web" or getattr(
            result, "prompt", None
        ) == "Search web"


class TestBuildFallbackPayload:
    def test_tier_1_validation_fallback(self, parser):
        payload = parser._build_fallback_payload(
            schema_class=GeneralistPayload,
            agent_enum=AgentEnum.GENERALIST,
            user_input="Tell me a joke",
        )

        assert isinstance(payload, GeneralistPayload)
        assert payload.action == DEFAULT_ACTION_MAP[AgentEnum.GENERALIST]

    def test_tier_2_construct_fallback_when_validation_fails(self, parser, monkeypatch):
        """Verify Tier 2 model_construct fallback when model_validate raises ValidationError."""

        def mock_validate(*args, **kwargs):
            raise ValidationError.from_exception_data(
                "validation error", line_errors=[]
            )

        monkeypatch.setattr(PlannerPayload, "model_validate", mock_validate)

        payload = parser._build_fallback_payload(
            schema_class=PlannerPayload,
            agent_enum=AgentEnum.PLANNER,
            user_input="Build backup pipeline",
        )

        assert isinstance(payload, PlannerPayload)
        assert payload.prompt == "Build backup pipeline"

    def test_tier_3_ultimate_fallback_on_construct_error(self, parser, monkeypatch):
        """Verify Tier 3 Generalist fallback when both model_validate and model_construct fail."""

        def mock_validate(*args, **kwargs):
            raise ValidationError.from_exception_data(
                "validation error", line_errors=[]
            )

        def mock_construct(*args, **kwargs):
            raise RuntimeError("Construct failed")

        monkeypatch.setattr(GeneralistPayload, "model_validate", mock_validate)
        monkeypatch.setattr(GeneralistPayload, "model_construct", mock_construct)

        payload = parser._build_fallback_payload(
            schema_class=GeneralistPayload,
            agent_enum=AgentEnum.GENERALIST,
            user_input="Emergency prompt",
        )

        assert isinstance(payload, GeneralistPayload)
        assert payload.prompt == "Emergency prompt"
