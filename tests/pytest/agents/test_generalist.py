"""tests/agents/test_generalist.py — Comprehensive Unit Tests for The Generalist Agent."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from charon.agents import get_agent_class
from charon.agents.generalist import TheGeneralist


@pytest.fixture
def generalist_agent():
    """Fixture providing a fresh instance of TheGeneralist with a mocked Ollama client."""
    with patch("charon.agents.generalist.agent.ollama.AsyncClient"), \
         patch("charon.agents.generalist.handlers.ollama.AsyncClient"):
        agent = TheGeneralist(model_name="llama3.1")
        agent.client = AsyncMock()
        yield agent


# -----------------------------------------------------------------------------
# 1. Answer Query Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_query_success(generalist_agent):
    """Test standard conversational query processing."""
    generalist_agent.client.generate = AsyncMock(
        return_value={"response": "Good evening, sir. How may I be of service?"}
    )

    result = await generalist_agent.execute(
        action="answer_query",
        parameters={"prompt": "Hello Charon"},
    )

    assert "Good evening, sir." in result
    generalist_agent.client.generate.assert_called_once()


@pytest.mark.asyncio
async def test_answer_query_streaming(generalist_agent):
    """Test query processing with token-by-token streaming callback."""
    tokens = ["Hello", " ", "there.", ""]

    async def mock_generator(*args, **kwargs):
        for token in tokens:
            yield {"response": token}

    generalist_agent.client.generate = AsyncMock(side_effect=mock_generator)

    streamed_output = []

    def callback(token: str):
        streamed_output.append(token)

    result = await generalist_agent.execute(
        action="answer_query",
        parameters={"prompt": "Greet me"},
        stream_callback=callback,
    )

    assert result == "Hello there."
    assert streamed_output == tokens


@pytest.mark.asyncio
async def test_answer_query_missing_prompt(generalist_agent):
    """Test guard clause when no prompt or query parameters are provided."""
    result = await generalist_agent.execute(
        action="answer_query",
        parameters={},
    )

    assert "Error: A 'prompt' or 'query' parameter is required." in result


# -----------------------------------------------------------------------------
# 2. RAG Synthesis Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_rag_success(generalist_agent):
    """Test RAG context synthesis handler combining context and query via answer_query."""
    generalist_agent.client.generate = AsyncMock(
        return_value={
            "response": "### ESP32 Pinout Specifications\n- Pin 1: VCC (3.3V)"
        }
    )

    result = await generalist_agent.execute(
        action="answer_query",
        parameters={
            "prompt": "What is pin 1?",
            "context": "ESP32 Board Pin 1 is connected to 3.3V VCC supply.",
        },
    )

    assert "ESP32 Pinout Specifications" in result
    generalist_agent.client.generate.assert_called_once()


# -----------------------------------------------------------------------------
# 3. Mathematical Evaluation Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_math_deterministic(generalist_agent):
    """Test pure arithmetic AST evaluation bypassing LLM inference."""
    result = await generalist_agent.execute(
        action="calculate_math",
        parameters={"expression": "(12 + 8) * 3 / 2"},
    )

    assert "Calculation Result: 30.0" in result
    generalist_agent.client.generate.assert_not_called()


@pytest.mark.asyncio
async def test_calculate_math_llm_fallback(generalist_agent):
    """Test mathematical reasoning fallback to LLM when AST parsing returns None."""
    generalist_agent.client.generate = AsyncMock(
        return_value={"response": "42"}
    )

    result = await generalist_agent.execute(
        action="calculate_math",
        parameters={"expression": "What is the sum of angles in a triangle?"},
    )

    assert "Calculation Result: 42" in result
    generalist_agent.client.generate.assert_called_once()


# -----------------------------------------------------------------------------
# 4. System Diagnostic & Shell Execution Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_info(generalist_agent):
    """Test gathering OS and system diagnostic metrics via system_task."""
    result = await generalist_agent.execute(
        action="system_task",
        parameters={"task": "system_info"},
    )

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_execute_system_command_raw_cli(generalist_agent):
    """Test executing a raw CLI shell command asynchronously."""
    mock_process = AsyncMock()
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"file1.py\n", b"file2.py\n", b""]
    )
    mock_process.wait = AsyncMock(return_value=None)
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        result = await generalist_agent.execute(
            action="execute_system_command",
            parameters={"command": "ls -la"},
        )

    assert "Command Execution Status: Success" in result
    assert "file1.py" in result


@pytest.mark.asyncio
async def test_execute_system_command_natural_language(generalist_agent):
    """Test synthesizing a CLI command from natural language prior to execution."""
    generalist_agent.client.generate = AsyncMock(
        return_value={"response": "pactl set-sink-volume @DEFAULT_SINK@ +10%"}
    )

    mock_process = AsyncMock()
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"Volume adjusted\n", b""]
    )
    mock_process.wait = AsyncMock(return_value=None)
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_shell:
        result = await generalist_agent.execute(
            action="execute_system_command",
            parameters={"command": "turn up the volume"},
        )

    generalist_agent.client.generate.assert_called_once()
    mock_shell.assert_called_once_with(
        "pactl set-sink-volume @DEFAULT_SINK@ +10%",
        stdout=-1,
        stderr=-2,
    )
    assert "Command Execution Status: Success" in result


@pytest.mark.asyncio
async def test_deterministic_guard_redirect(generalist_agent):
    """Test deterministic guard redirecting answer_query to system execution on OS keywords."""
    generalist_agent.client.generate = AsyncMock(
        return_value={"response": "amixer set Master mute"}
    )

    mock_process = AsyncMock()
    mock_process.stdout.readline = AsyncMock(
        side_effect=[b"Muted\n", b""]
    )
    mock_process.wait = AsyncMock(return_value=None)
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        result = await generalist_agent.execute(
            action="answer_query",
            parameters={"prompt": "please mute the sound"},
        )

    assert "Command Execution Status: Success" in result


# -----------------------------------------------------------------------------
# 5. Routing & Integration Gateway Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledge_action(generalist_agent):
    """Test acknowledge action returning static Concierge response."""
    result = await generalist_agent.execute(
        action="acknowledge",
        parameters={},
    )

    assert "Your directive has been noted." in result


@pytest.mark.asyncio
async def test_unknown_action_fallback(generalist_agent):
    """Test unknown action gracefully falling back to standard query processing."""
    generalist_agent.client.generate = AsyncMock(
        return_value={"response": "Fallback query response."}
    )

    result = await generalist_agent.execute(
        action="unregistered_action",
        parameters={"prompt": "Who is the concierge?"},
    )

    assert "Fallback query response." in result


def test_lazy_loading_gateway():
    """Test dynamic agent resolving via get_agent_class gateway."""
    agent_cls = get_agent_class("generalist")
    assert agent_cls is TheGeneralist

    agent_cls_alias = get_agent_class("TheGeneralist")
    assert agent_cls_alias is TheGeneralist
