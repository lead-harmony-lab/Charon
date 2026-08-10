"""
tests/core/test_dispatcher.py — Comprehensive unit tests for charon.core.dispatcher.AgentDispatcher
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from charon.core.dispatcher import AgentDispatcher
from charon.intent import AgentEnum, StewardPayload


# --- Test Models ---

class DummyExtraction(BaseModel):
    action: str = "custom_action"
    requires_approval: bool = False
    query: str = "Test query string"


class DummyMemoryCandidate(BaseModel):
    fact: str = "User prefers dark mode."
    is_persistent: bool = True
    category: str = "user_preference"


class DummyExtractionWithMemory(BaseModel):
    action: str = "acknowledge"
    requires_approval: bool = False
    memory_candidate: DummyMemoryCandidate = Field(default_factory=DummyMemoryCandidate)


class DummyExtractionWithRule(BaseModel):
    action: str = "acknowledge"
    rule: str = "Existing rule"
    memory_candidate: DummyMemoryCandidate = Field(default_factory=DummyMemoryCandidate)


class CustomPayload(BaseModel):
    action: str = "custom_action"
    query: str = "Custom test query"
    extra_field: str = "extra_value"


# --- Fixtures ---

@pytest.fixture
def mock_archivist():
    archivist = MagicMock()
    archivist.execute = MagicMock(return_value="Archivist result")
    return archivist


@pytest.fixture
def dispatcher(mock_archivist):
    return AgentDispatcher(
        db_path=Path("/tmp/charon_test_db"),
        heavy_model="llama3.1",
        archivist=mock_archivist,
    )


# --- Tests: Agent Resolution (_resolve_agent) ---

def test_resolve_agent_enum_inputs(dispatcher):
    """Verifies agent resolution when explicit AgentEnum values are supplied."""
    enums_to_test = [
        AgentEnum.PLANNER,
        AgentEnum.ENGINEER,
        AgentEnum.GENERALIST,
        AgentEnum.ARCHIVIST,
        AgentEnum.OVERSEER,
        AgentEnum.CLEANER,
        AgentEnum.MACHINIST,
        AgentEnum.SPARK,
        AgentEnum.QUARTERMASTER,
        AgentEnum.SCOUT,
    ]
    for agent_enum in enums_to_test:
        resolved = dispatcher._resolve_agent(agent_enum)
        assert resolved is not None


def test_resolve_agent_steward_adapter(dispatcher):
    """Verifies StewardAdapter construction and execution path."""
    with patch("charon.agents.steward.execute_steward_task", return_value="Light state set"):
        resolved = dispatcher._resolve_agent(AgentEnum.STEWARD)
        result = resolved.execute(
            action="control_appliance",
            parameters={"target_device": "light.light1", "command": "turn_on"}
        )
        assert result == "Light state set"


def test_resolve_agent_string_resolution(dispatcher):
    """Verifies string-based lookup, fallback loops, and unknown identifier behavior."""
    # Direct match with prefix stripping
    resolved = dispatcher._resolve_agent("THE_ENGINEER")
    from charon.agents.engineer import TheEngineer
    assert isinstance(resolved, TheEngineer)

    # String lookup (lowercase / mixed case)
    resolved_val = dispatcher._resolve_agent("steward")
    assert resolved_val is not None

    # Invalid string -> fallback to GENERALIST
    fallback = dispatcher._resolve_agent("NON_EXISTENT_AGENT_XYZ")
    from charon.agents.generalist import TheGeneralist
    assert isinstance(fallback, TheGeneralist)


def test_resolve_agent_value_lookup_fallback(dispatcher):
    """Covers line 40/45: Fallback to AgentEnum(agent) value lookup when key lookup raises KeyError."""
    with patch.object(AgentEnum, "__getitem__", side_effect=KeyError("forced_key_error")):
        resolved = dispatcher._resolve_agent("The_Engineer")
        from charon.agents.engineer import TheEngineer
        assert isinstance(resolved, TheEngineer)


def test_resolve_agent_unmatched_enum_fallback(dispatcher):
    """Verifies fallback when an unhandled Enum variant is provided."""
    resolved = dispatcher._resolve_agent(AgentEnum.ARCHITECT)
    from charon.agents.generalist import TheGeneralist
    assert isinstance(resolved, TheGeneralist)


def test_resolve_agent_non_string_non_enum_fallback(dispatcher):
    """Verifies fallback to GENERALIST when input is neither string nor AgentEnum (covers line 45)."""
    resolved = dispatcher._resolve_agent(12345)
    from charon.agents.generalist import TheGeneralist
    assert isinstance(resolved, TheGeneralist)


# --- Tests: Execution Dispatcher (dispatch) ---

@pytest.mark.asyncio
async def test_dispatch_steward_with_steward_payload(dispatcher):
    payload = StewardPayload(action="control_appliance", device_id="lamp", command="turn_on")
    with patch("charon.agents.steward.execute_steward_task", return_value="Lamp turned on"):
        res = await dispatcher.dispatch(AgentEnum.STEWARD, payload, "Turn on lamp")
        assert res == "Lamp turned on"


@pytest.mark.asyncio
async def test_dispatch_steward_with_generic_payload(dispatcher):
    extraction = DummyExtraction(action="control_appliance")
    with patch("charon.agents.steward.execute_steward_task", return_value="Switch toggled"):
        res = await dispatcher.dispatch(AgentEnum.STEWARD, extraction, "Toggle switch")
        assert res == "Switch toggled"


@pytest.mark.asyncio
async def test_dispatch_overseer(dispatcher):
    with patch("charon.agents.overseer.TheOverseer.execute", return_value="Overseer report"):
        res = await dispatcher.dispatch(AgentEnum.OVERSEER, DummyExtraction(), "Check status")
        assert res == "Overseer report"


@pytest.mark.asyncio
async def test_dispatch_archivist_rag_search(dispatcher, mock_archivist):
    mock_archivist.execute.return_value = "Retrieved doc text"
    with patch("charon.agents.generalist.TheGeneralist.execute", return_value="RAG Summary") as mock_gen:
        res = await dispatcher.dispatch(
            AgentEnum.ARCHIVIST,
            DummyExtraction(action="search_datasheets"),
            "Find datasheet",
        )
        assert res == "RAG Summary"
        mock_gen.assert_called_once_with(
            action="synthesize_rag",
            parameters={"query": "Test query string", "context": "Retrieved doc text"},
            stream_callback=None,
        )


@pytest.mark.asyncio
async def test_dispatch_archivist_async_and_non_rag(dispatcher, mock_archivist):
    async def async_archivist_res(*args, **kwargs):
        return "Async Archivist Record"

    mock_archivist.execute = MagicMock(side_effect=async_archivist_res)

    res = await dispatcher.dispatch(
        AgentEnum.ARCHIVIST,
        DummyExtraction(action="store_record"),
        "Save record",
    )
    assert res == "Async Archivist Record"


@pytest.mark.asyncio
async def test_dispatch_specialist_agents(dispatcher):
    """Verifies routing across all remaining specialist agents."""
    agents_and_patches = [
        (AgentEnum.PLANNER, "charon.agents.planner.ThePlanner.execute", "Planner DAG"),
        (AgentEnum.ENGINEER, "charon.agents.engineer.TheEngineer.execute", "Engineer Code"),
        (AgentEnum.CLEANER, "charon.agents.cleaner.TheCleaner.execute", "Clean Workspace"),
        (AgentEnum.GENERALIST, "charon.agents.generalist.TheGeneralist.execute", "General Answer"),
        (AgentEnum.MACHINIST, "charon.agents.machinist.TheMachinist.execute", "Machinist Path"),
        (AgentEnum.SPARK, "charon.agents.spark.TheSpark.execute", "Spark Circuit"),
        (AgentEnum.QUARTERMASTER, "charon.agents.quartermaster.TheQuartermaster.execute", "BOM Generated"),
        (AgentEnum.SCOUT, "charon.agents.scout.TheScout.execute", "Scout Results"),
    ]

    for agent_enum, patch_path, return_val in agents_and_patches:
        with patch(patch_path, return_value=return_val):
            res = await dispatcher.dispatch(agent_enum, DummyExtraction(), "Execute task")
            assert res == return_val


@pytest.mark.asyncio
async def test_dispatch_architect_and_default_fallback(dispatcher):
    res_arch = await dispatcher.dispatch(AgentEnum.ARCHITECT, None, "Update state")
    assert res_arch == "Internal state updated."

    # Test unknown/unhandled enum option
    fake_enum = MagicMock()
    fake_enum.value = "CUSTOM_AGENT"
    res_fallback = await dispatcher.dispatch(fake_enum, None, "Do something")
    assert res_fallback == "Agent CUSTOM_AGENT execution complete."


@pytest.mark.asyncio
async def test_dispatch_async_result_awaiting(dispatcher):
    """Verifies that awaitable returns from agent execution are correctly awaited."""
    async def async_exec(*args, **kwargs):
        return "Async execution response"

    with patch("charon.agents.generalist.TheGeneralist.execute", side_effect=async_exec):
        res = await dispatcher.dispatch(AgentEnum.GENERALIST, None, "Async test prompt")
        assert res == "Async execution response"


@pytest.mark.asyncio
async def test_dispatch_memory_candidate_branches(dispatcher, mock_archivist):
    # Branch 1: Memory candidate injected into params as 'fact'
    extraction = DummyExtractionWithMemory()
    with patch("charon.agents.generalist.TheGeneralist.execute", return_value="OK"):
        await dispatcher.dispatch(AgentEnum.GENERALIST, extraction, "Remember dark mode")
        mock_archivist.execute.assert_called_once_with(
            "store_record",
            {"fact": "User prefers dark mode.", "category": "user_preference"},
            raw_prompt="Remember dark mode",
        )

    # Branch 2: Memory candidate skipped when 'rule' is already present
    mock_archivist.reset_mock()
    extraction_rule = DummyExtractionWithRule()
    with patch("charon.agents.generalist.TheGeneralist.execute", return_value="OK"):
        await dispatcher.dispatch(AgentEnum.GENERALIST, extraction_rule, "Set rule")
        mock_archivist.execute.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_fallback_text_parameters(dispatcher):
    """Verifies raw user input populates parameter dictionary when no valid text fields exist."""
    class EmptyPayload(BaseModel):
        action: str = "answer_query"
        requires_approval: bool = False

    with patch("charon.agents.generalist.TheGeneralist.execute") as mock_exec:
        mock_exec.return_value = "Answered"
        await dispatcher.dispatch(AgentEnum.GENERALIST, EmptyPayload(), "Raw fallback query")

        args, kwargs = mock_exec.call_args
        params = args[1] if len(args) > 1 else kwargs.get("parameters", {})
        assert params.get("prompt") == "Raw fallback query"
        assert params.get("query") == "Raw fallback query"


# --- Tests: Edge Cases for 100% Coverage ---

def test_dispatcher_default_initialization():
    """Executes default initialization branch by instantiating AgentDispatcher with archivist=None."""
    with patch("charon.core.dispatcher.TheArchivist") as mock_archivist_cls:
        dispatcher_default = AgentDispatcher(
            db_path=Path("/tmp/charon_test_db"),
            heavy_model="llama3.1",
            archivist=None,
        )
        assert dispatcher_default is not None
        assert dispatcher_default.archivist is not None
        mock_archivist_cls.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_with_stream_callback(dispatcher):
    """Verifies that stream_cb is passed down to agent execution."""
    callback_mock = MagicMock()
    with patch("charon.agents.generalist.TheGeneralist.execute", return_value="Streamed") as mock_exec:
        res = await dispatcher.dispatch(
            AgentEnum.GENERALIST,
            DummyExtraction(),
            "Stream test",
            stream_cb=callback_mock,
        )
        assert res == "Streamed"
        assert mock_exec.call_args.kwargs.get("stream_callback") == callback_mock


@pytest.mark.asyncio
async def test_dispatch_custom_base_model_payload(dispatcher):
    """Verifies dispatcher handling when payload is a custom BaseModel."""
    payload = CustomPayload()
    with patch("charon.agents.generalist.TheGeneralist.execute", return_value="Custom handled") as mock_exec:
        res = await dispatcher.dispatch(AgentEnum.GENERALIST, payload, "Raw query")
        assert res == "Custom handled"
        params = mock_exec.call_args.kwargs.get("parameters") or mock_exec.call_args.args[1]
        assert params["query"] == "Custom test query"
        assert params["extra_field"] == "extra_value"


@pytest.mark.asyncio
async def test_dispatch_agent_without_callable_execute(dispatcher):
    """Verifies fallback message when resolved agent execute attribute is not callable (covers line 182)."""
    with patch.object(dispatcher, "_resolve_agent", return_value=object()):
        result = await dispatcher.dispatch(
            agent_enum=AgentEnum.GENERALIST,
            extraction=None,
            user_raw_input="hello",
        )
        assert result == "Agent The_Generalist execution complete."
