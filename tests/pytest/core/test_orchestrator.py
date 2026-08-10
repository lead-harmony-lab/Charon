"""
tests/test_orchestrator.py — Unit tests for charon.core.orchestrator.Orchestrator
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from charon.config.paths import CHROMA_DB_DIR
from charon.core.session import SessionGateway
from charon.intent import AgentEnum, RoutingPayload


# --- Fixtures ---

@pytest.fixture
def mock_dependencies():
    with patch("charon.core.session.py.ollama.AsyncClient"), \
         patch("charon.core.session.py.TheArchivist") as mock_archivist_cls, \
         patch("charon.core.session.py.IntentParser") as mock_parser_cls, \
         patch("charon.core.session.py.AgentDispatcher") as mock_dispatcher_cls:
        mock_archivist = MagicMock()
        mock_parser = AsyncMock()
        mock_dispatcher = AsyncMock()

        mock_archivist_cls.return_value = mock_archivist
        mock_parser_cls.return_value = mock_parser
        mock_dispatcher_cls.return_value = mock_dispatcher

        yield {
            "archivist": mock_archivist,
            "parser": mock_parser,
            "dispatcher": mock_dispatcher,
        }


@pytest.fixture
def orchestrator(mock_dependencies):
    return SessionGateway(
        db_path=Path("/tmp/charon_test_db"),
        heavy_model="llama3.1",
        triage_model="llama3.1",
    )


# --- Tests ---

def test_orchestrator_init_default_db_path(mock_dependencies):
    """Covers default initialization when db_path is None."""
    orch = SessionGateway()
    assert orch.db_path == Path(CHROMA_DB_DIR)


def test_record_turn(orchestrator):
    orchestrator.memory = MagicMock()
    orchestrator.record_turn("User request", "Agent response")

    if hasattr(orchestrator.memory, "add_turn"):
        orchestrator.memory.add_turn.assert_called_once_with("User request", "Agent response")


def test_record_turn_append_fallback(orchestrator):
    """Covers the memory fallback branch using .append()."""
    class LegacyMemory:
        def __init__(self):
            self.history = []

        def append(self, item):
            self.history.append(item)

    orchestrator.memory = LegacyMemory()
    orchestrator.record_turn("User request", "Agent response")
    assert orchestrator.memory.history == [{"user": "User request", "assistant": "Agent response"}]


def test_record_turn_no_matching_methods(orchestrator):
    """Covers the 61->exit branch where memory has neither add_turn nor append."""
    class UnsupportedMemory:
        pass

    orchestrator.memory = UnsupportedMemory()
    # Runs cleanly without raising exceptions or modifying history
    orchestrator.record_turn("User request", "Agent response")


@pytest.mark.asyncio
async def test_get_ledger_context_success(orchestrator, mock_dependencies):
    mock_archivist = mock_dependencies["archivist"]
    mock_archivist.execute.return_value = "System rule: Always use metric units."

    context = await orchestrator.get_ledger_context("3D printer speeds")

    assert "System rule: Always use metric units." in context
    mock_archivist.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_ledger_context_awaitable_result(orchestrator, mock_dependencies):
    """Covers the inspect.isawaitable branch when archivist returns a Coroutine."""
    mock_archivist = mock_dependencies["archivist"]

    async def mock_async_execute(*args, **kwargs):
        return "Async system rule: Use 24V power supply."

    mock_archivist.execute.side_effect = mock_async_execute

    context = await orchestrator.get_ledger_context("Voltage specs")
    assert context == "Async system rule: Use 24V power supply."


@pytest.mark.asyncio
async def test_get_ledger_context_exception_fallback(orchestrator, mock_dependencies):
    mock_archivist = mock_dependencies["archivist"]
    mock_archivist.execute.side_effect = Exception("DB Connection Refused")

    context = await orchestrator.get_ledger_context("Test input")
    assert context == "No specific system rules recorded."


@pytest.mark.asyncio
async def test_parse_routing_delegation(orchestrator, mock_dependencies):
    mock_parser = mock_dependencies["parser"]
    expected_routing = RoutingPayload(agent=AgentEnum.SPARK, reasoning="Firmware operation")
    mock_parser.parse_routing.return_value = expected_routing

    result = await orchestrator.parse_routing("Flash ESP32 firmware")
    assert result == expected_routing
    mock_parser.parse_routing.assert_called_once_with("Flash ESP32 firmware", None)


@pytest.mark.asyncio
async def test_parse_extraction_delegation(orchestrator, mock_dependencies):
    """Covers parse_extraction delegation."""
    mock_parser = mock_dependencies["parser"]
    mock_archivist = mock_dependencies["archivist"]
    mock_archivist.execute.return_value = "System rules context"
    mock_parser.parse_extraction.return_value = MagicMock()

    result = await orchestrator.parse_extraction("Compile code", AgentEnum.ENGINEER)

    assert result == mock_parser.parse_extraction.return_value
    mock_parser.parse_extraction.assert_called_once_with(
        "Compile code", AgentEnum.ENGINEER, "System rules context"
    )


@pytest.mark.asyncio
async def test_execute_agent_task_flow(orchestrator, mock_dependencies):
    mock_dispatcher = mock_dependencies["dispatcher"]
    mock_dispatcher.dispatch.return_value = "Task execution success"

    result = await orchestrator.execute_agent_task(
        agent="The_Spark",
        extraction=None,
        user_raw_input="Compile C code",
    )

    assert result == "Task execution success"
    mock_dispatcher.dispatch.assert_called_once_with(
        agent_enum=AgentEnum.SPARK,
        extraction=None,
        user_raw_input="Compile C code",
        stream_cb=None,
    )


def test_get_acknowledgment(orchestrator):
    ack = orchestrator.get_acknowledgment(AgentEnum.SPARK)
    assert isinstance(ack, str)
    assert len(ack) > 0


def test_get_acknowledgment_string_agent(orchestrator):
    """Covers passing agent as string representation."""
    ack = orchestrator.get_acknowledgment("The_Spark")
    assert isinstance(ack, str)
    assert len(ack) > 0