#!/usr/bin/env python3
"""tests/core/test_engine.py — Unit tests for charon.core.engine.OrchestrationEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from charon.core.engine import OrchestrationEngine
from charon.intent import AgentEnum, RoutingPayload


# --- Fixtures ---

@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    orchestrator.parse_routing = AsyncMock()
    orchestrator.parse_extraction = AsyncMock()
    orchestrator.execute_agent_task = AsyncMock()
    orchestrator.get_acknowledgment = MagicMock(return_value="On it, captain.")
    orchestrator.record_turn = MagicMock()
    orchestrator.dispatcher = MagicMock()
    orchestrator.dispatcher._resolve_agent = MagicMock()
    return orchestrator


@pytest.fixture
def engine(mock_orchestrator):
    return OrchestrationEngine(orchestrator=mock_orchestrator)


# Helper matcher for test assertions
class AnyExtractionMatcher:
    def __eq__(self, other):
        return True

ANY_EXTRACTION = AnyExtractionMatcher()


# --- Tests: Initialization ---

def test_init_default_orchestrator():
    """Tests initializing OrchestrationEngine with default Orchestrator construction."""
    with patch("charon.core.engine.Orchestrator") as mock_orch_class:
        mock_instance = MagicMock()
        mock_orch_class.return_value = mock_instance

        engine_inst = OrchestrationEngine()
        assert engine_inst.orchestrator == mock_instance
        mock_orch_class.assert_called_once()


# --- Tests: Request Processing & Routing ---

@pytest.mark.asyncio
async def test_process_request_empty_prompt(engine):
    """Tests empty prompt handling."""
    result = await engine.process_request("   ")
    assert result == "Error: Empty prompt received."


@pytest.mark.asyncio
async def test_process_request_agent_override_valid(engine, mock_orchestrator):
    """Tests valid explicit agent override bypassing routing."""
    mock_orchestrator.execute_agent_task.return_value = "Override Execution Result"

    result = await engine.process_request(
        user_input="Run diagnostics",
        agent_override="The_Overseer",
    )

    assert result == "Override Execution Result"
    mock_orchestrator.parse_routing.assert_not_called()
    mock_orchestrator.execute_agent_task.assert_called_once()


@pytest.mark.asyncio
async def test_process_request_agent_override_invalid_falls_back(engine, mock_orchestrator):
    """Tests invalid agent override falling back to triage routing."""
    mock_orchestrator.parse_routing.return_value = RoutingPayload(
        agent=AgentEnum.GENERALIST,
        needs_decomposition=False,
    )
    mock_orchestrator.execute_agent_task.return_value = "Fallback Result"

    result = await engine.process_request(
        user_input="Hello Charon",
        agent_override="INVALID_OVERRIDE",
    )

    assert result == "Fallback Result"
    mock_orchestrator.parse_routing.assert_called_once()


@pytest.mark.asyncio
async def test_process_request_routing_returns_none_defaults_to_generalist(engine, mock_orchestrator):
    """Hits missing lines: Tests parse_routing returning None falling back to AgentEnum.GENERALIST."""
    mock_orchestrator.parse_routing.return_value = None
    mock_orchestrator.execute_agent_task.return_value = "Generalist Triage Fallback"

    result = await engine.process_request("Unroutable generic query")

    assert result == "Generalist Triage Fallback"
    mock_orchestrator.execute_agent_task.assert_called_once_with(
        agent=AgentEnum.GENERALIST,
        extraction=ANY_EXTRACTION,
        user_raw_input="Unroutable generic query",
        stream_cb=None,
    )


@pytest.mark.asyncio
async def test_process_request_standard_routing_single_turn(engine, mock_orchestrator):
    """Tests standard single-turn routing with streaming callback enabled."""
    mock_orchestrator.parse_routing.return_value = RoutingPayload(
        agent=AgentEnum.MACHINIST,
        needs_decomposition=False,
    )
    mock_orchestrator.parse_extraction.return_value = {"action": "slice"}
    mock_orchestrator.execute_agent_task.return_value = "GCode generated"

    stream_chunks = []

    result = await engine.process_request(
        user_input="Slice my bracket model",
        stream_cb=stream_chunks.append,
    )

    assert result == "GCode generated"
    assert stream_chunks[0] == "[On it, captain.]\n\n"
    mock_orchestrator.execute_agent_task.assert_called_once_with(
        agent=AgentEnum.MACHINIST,
        extraction={"action": "slice"},
        user_raw_input="Slice my bracket model",
        stream_cb=stream_chunks.append,
    )


@pytest.mark.asyncio
async def test_process_request_routing_fallback_to_primary_agent(engine, mock_orchestrator):
    """Tests fallback to 'primary_agent' attribute when 'agent' is missing on routing object."""
    mock_routing = MagicMock(spec=[])
    mock_routing.primary_agent = AgentEnum.QUARTERMASTER
    mock_routing.needs_decomposition = False
    mock_orchestrator.parse_routing.return_value = mock_routing
    mock_orchestrator.execute_agent_task.return_value = "Inventory checked"

    result = await engine.process_request("Check stock")

    assert result == "Inventory checked"
    mock_orchestrator.execute_agent_task.assert_called_once_with(
        agent=AgentEnum.QUARTERMASTER,
        extraction=ANY_EXTRACTION,
        user_raw_input="Check stock",
        stream_cb=None,
    )


# --- Tests: Multi-step DAG Execution & Planner Fallbacks ---

@pytest.mark.asyncio
async def test_execute_plan_sequence_execution_with_sync_and_async_steps(engine, mock_orchestrator):
    """Tests complete DAG sequence execution with synchronous step outputs and parameter substitution."""
    mock_planner = MagicMock()
    # Planner returning non-awaitable (sync) list
    mock_planner.execute.return_value = [
        {"step": 1, "agent": "The_Scout", "action": "search_web", "parameters": {"query": "ESP32 pinout"}},
        {"step": 2, "agent": "The_Spark", "action": "compile_firmware", "parameters": {"context": "$STEP_1_OUTPUT"}},
    ]

    mock_scout = MagicMock()
    # Synchronous step return value
    mock_scout.execute.return_value = "Scout Output Pinout Data"

    mock_spark = MagicMock()
    # Asynchronous step return value
    mock_spark.execute = AsyncMock(return_value="Firmware Binary Compiled")

    def resolve_agent_side_effect(agent_name):
        if agent_name in (AgentEnum.PLANNER, "The_Planner"):
            return mock_planner
        elif agent_name == "The_Scout":
            return mock_scout
        elif agent_name == "The_Spark":
            return mock_spark
        return MagicMock()

    mock_orchestrator.dispatcher._resolve_agent.side_effect = resolve_agent_side_effect
    mock_orchestrator.parse_routing.return_value = RoutingPayload(
        agent=AgentEnum.PLANNER,
        needs_decomposition=True,
    )

    stream_chunks = []
    result = await engine.process_request("Search pinout and build firmware", stream_cb=stream_chunks.append)

    assert "Scout Output Pinout Data" in result
    assert "Firmware Binary Compiled" in result
    assert any("Execution Blueprint" in chunk for chunk in stream_chunks)
    assert any("Step 1: `The_Scout`" in chunk for chunk in stream_chunks)
    mock_orchestrator.record_turn.assert_called_once()


@pytest.mark.asyncio
async def test_execute_plan_sequence_string_agent_trigger(engine, mock_orchestrator):
    """Tests triggering DAG execution via string "The_Planner" target_agent."""
    mock_routing = MagicMock()
    mock_routing.agent = "The_Planner"
    mock_routing.needs_decomposition = False
    mock_orchestrator.parse_routing.return_value = mock_routing

    mock_planner = MagicMock()
    mock_planner.execute = AsyncMock(return_value="Non-list response")  # Invalid plan format
    mock_orchestrator.dispatcher._resolve_agent.return_value = mock_planner
    mock_orchestrator.execute_agent_task.return_value = "Single turn fallback output"

    result = await engine.process_request("Create plan")

    assert result == "Single turn fallback output"


@pytest.mark.asyncio
async def test_execute_plan_sequence_planner_invalid_plan_fallback(engine, mock_orchestrator):
    """Tests falling back to single-turn execution when Planner returns non-list or empty list."""
    mock_planner = MagicMock()
    mock_planner.execute = AsyncMock(return_value=[])  # Empty list
    mock_orchestrator.dispatcher._resolve_agent.return_value = mock_planner

    mock_orchestrator.parse_routing.return_value = RoutingPayload(
        agent=AgentEnum.PLANNER,
        needs_decomposition=True,
    )
    mock_orchestrator.execute_agent_task.return_value = "Fallback Single Planner Execution"

    result = await engine.process_request("Plan complex build")

    assert result == "Fallback Single Planner Execution"


@pytest.mark.asyncio
async def test_execute_plan_sequence_step_raises_exception(engine, mock_orchestrator):
    """Tests exception handling during step execution triggering self-healing recovery."""
    mock_planner = MagicMock()
    # Sync returns for diagnosis and planner
    mock_planner.execute.side_effect = [
        [{"step": 1, "agent": "The_Engineer", "action": "generate_cad"}],
        "Diagnostic Recommendation: Check CadQuery syntax",
    ]

    mock_engineer = MagicMock()
    mock_engineer.execute.side_effect = RuntimeError("CadQuery syntax error at line 4")

    def resolve_agent_side_effect(agent_name):
        if agent_name in (AgentEnum.PLANNER, "The_Planner"):
            return mock_planner
        return mock_engineer

    mock_orchestrator.dispatcher._resolve_agent.side_effect = resolve_agent_side_effect
    mock_orchestrator.parse_routing.return_value = RoutingPayload(
        agent=AgentEnum.PLANNER,
        needs_decomposition=True,
    )

    result = await engine.process_request("Generate 3D box model")

    assert "[Runtime Error]: Execution aborted due to unhandled exception: CadQuery syntax error at line 4" in result
    assert "[Self-Healing Recovery Intercept]:" in result
    assert "Diagnostic Recommendation: Check CadQuery syntax" in result


# --- Tests: Self-Healing & Parameter Resolution ---

@pytest.mark.asyncio
async def test_handle_self_healing_no_error_returns_cleanly(engine):
    """Tests that step results without error keywords skip self-healing."""
    result = await engine._handle_self_healing_if_needed(
        step_num=1,
        agent_name="The_Generalist",
        step_result="Step completed with success.",
        raw_prompt="Hello",
    )
    assert result == "Step completed with success."


@pytest.mark.asyncio
async def test_handle_self_healing_diagnosis_raises_exception(engine, mock_orchestrator):
    """Tests self-healing handling when the diagnostic call itself fails."""
    mock_planner = MagicMock()
    mock_planner.execute = AsyncMock(side_effect=Exception("LLM Context Limit Exceeded"))
    mock_orchestrator.dispatcher._resolve_agent.return_value = mock_planner

    stream_chunks = []
    error_log = "Error: System failed to execute command"

    result = await engine._handle_self_healing_if_needed(
        step_num=1,
        agent_name="The_Spark",
        step_result=error_log,
        raw_prompt="Flash MCU",
        stream_cb=stream_chunks.append,
    )

    assert "[Self-Healing Failed]: LLM Context Limit Exceeded" in result
    assert any("⚠️ *Step execution failed." in chunk for chunk in stream_chunks)


def test_resolve_step_references(engine):
    """Tests string substitution and non-string parameter resilience in _resolve_step_references."""
    parameters = {
        "str_param": "Result from step 1: $STEP_1_OUTPUT",
        "int_param": 42,
        "bool_param": True,
        "unused_placeholder": "Static text with $STEP_99_OUTPUT",
    }
    history = [
        {"step": 1, "output": "DataFromStep1"},
    ]

    resolved = engine._resolve_step_references(parameters, history)

    assert resolved["str_param"] == "Result from step 1: DataFromStep1"
    assert resolved["int_param"] == 42
    assert resolved["bool_param"] is True
    assert resolved["unused_placeholder"] == "Static text with $STEP_99_OUTPUT"
