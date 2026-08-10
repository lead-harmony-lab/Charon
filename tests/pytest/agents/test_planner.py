"""Unit tests for ThePlanner agent and its submodules."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from charon.agents.planner import ACTION_MAP, VALID_PLANNER_ACTIONS, ThePlanner


@pytest.fixture
def planner():
    """Fixture providing an instance of ThePlanner with a mocked Ollama client."""
    with patch("charon.agents.planner.agent.ollama.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        agent = ThePlanner(model_name="llama3.1")
        agent.client = mock_client
        yield agent


# ============================================================================
# 1. INITIALIZATION & METADATA TESTS
# ============================================================================


def test_planner_initialization(planner):
    """Verify default initialization parameters and valid planner actions."""
    assert planner.model_name == "llama3.1"
    assert planner.python_cmd is not None
    assert isinstance(VALID_PLANNER_ACTIONS, tuple)
    assert "decompose_task" in VALID_PLANNER_ACTIONS
    assert "draft_build_sequence" in VALID_PLANNER_ACTIONS
    assert "analyze_error_logs" in VALID_PLANNER_ACTIONS
    assert "execute_sandbox_code" in VALID_PLANNER_ACTIONS


def test_action_map_aliases():
    """Verify alias mapping correctly normalizes action names."""
    assert ACTION_MAP["decompose"] == "decompose_task"
    assert ACTION_MAP["plan"] == "draft_build_sequence"
    assert ACTION_MAP["diagnose"] == "analyze_error_logs"
    assert ACTION_MAP["sandbox"] == "execute_sandbox_code"


# ============================================================================
# 2. TASK DECOMPOSITION TESTS (dag.py)
# ============================================================================


@pytest.mark.asyncio
async def test_decompose_task_success(planner):
    """Test successful task decomposition into a JSON DAG execution sequence."""
    mock_dag = [
        {
            "step": 1,
            "agent": "The_Archivist",
            "action": "search_ledger",
            "parameters": {"query": "CAD standards"},
        },
        {
            "step": 2,
            "agent": "The_Cleaner",
            "action": "initialize_project_workspace",
            "parameters": {"project_name": "rover"},
        },
    ]
    planner.client.generate.return_value = {"response": json.dumps(mock_dag)}

    result = await planner.execute(
        action="decompose_task",
        params={"objective": "Set up rover project based on CAD standards"},
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["agent"] == "The_Archivist"
    assert result[1]["agent"] == "The_Cleaner"
    planner.client.generate.assert_called_once()


@pytest.mark.asyncio
async def test_decompose_task_markdown_codeblock_parsing(planner):
    """Test handling of raw LLM outputs enclosed in markdown JSON blocks."""
    raw_response = (
        "```json\n"
        '[\n  {"step": 1, "agent": "The_Scout", "action": "web_search", "parameters": {"query": "test"}}\n]\n'
        "```"
    )
    planner.client.generate.return_value = {"response": raw_response}

    result = await planner.execute(
        action="decompose",  # Using alias
        params={"objective": "Search test"},
    )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["agent"] == "The_Scout"


@pytest.mark.asyncio
async def test_decompose_task_empty_objective(planner):
    """Test handling when no objective or prompt is provided."""
    result = await planner.execute(action="decompose_task", params={})
    assert result == []
    planner.client.generate.assert_not_called()


# ============================================================================
# 3. ENGINEERING SEQUENCE DRAFTING TESTS (sequencing.py)
# ============================================================================


@pytest.mark.asyncio
async def test_draft_build_sequence_success(planner):
    """Test drafting an engineering build sequence without streaming."""
    expected_plan = (
        "## 1. OBJECTIVE SUMMARY\n"
        "Build a CAD bracket.\n\n"
        "## 2. ARCHITECTURE & COMPONENT BREAKDOWN\n"
        "- cad/bracket.py\n"
    )
    planner.client.generate.return_value = {"response": expected_plan}

    result = await planner.execute(
        action="plan",  # Using alias
        params={"objective": "Design a bracket"},
    )

    assert "OBJECTIVE SUMMARY" in result
    assert "cad/bracket.py" in result


@pytest.mark.asyncio
async def test_draft_build_sequence_streaming(planner):
    """Test streaming callback execution during sequence drafting."""
    chunks = ["Building ", "blueprint... ", "Done."]

    async def mock_stream_generator(*args, **kwargs):
        for chunk in chunks:
            yield {"response": chunk}

    planner.client.generate.side_effect = mock_stream_generator

    received_tokens = []

    def callback(token: str):
        received_tokens.append(token)

    result = await planner.execute(
        action="draft_build_sequence",
        params={"objective": "Stream plan"},
        stream_callback=callback,
    )

    assert result == "Building blueprint... Done."
    assert received_tokens == ["Building ", "blueprint... ", "Done."]


# ============================================================================
# 4. DIAGNOSTICS & ERROR LOG ANALYSIS TESTS (diagnostics.py)
# ============================================================================


@pytest.mark.asyncio
async def test_analyze_error_logs_success(planner):
    """Test log analysis with mock compiler/runtime error logs."""
    planner.client.generate.return_value = {
        "response": "Root cause: SyntaxError on line 12. Solution: Add missing colon."
    }

    result = await planner.execute(
        action="diagnose",  # Using alias
        params={"log_content": "SyntaxError: invalid syntax at line 12"},
    )

    assert "Log Analysis:" in result
    assert "Root cause: SyntaxError" in result


@pytest.mark.asyncio
async def test_analyze_error_logs_missing_content(planner):
    """Test response when error log content is missing."""
    result = await planner.execute(action="analyze_error_logs", params={})
    assert "Error: 'log_content' is required" in result


# ============================================================================
# 5. SANDBOX CODE EXECUTION TESTS (sandbox.py)
# ============================================================================


@pytest.mark.asyncio
async def test_execute_sandbox_code_success(planner, tmp_path):
    """Test generating and executing python code in subshell sandbox."""
    generated_python_code = (
        "```python\n"
        "import sys\n"
        "print('Sandbox execution verified.')\n"
        "```"
    )
    planner.client.generate.return_value = {"response": generated_python_code}

    with patch(
        "charon.agents.planner.sandbox.extract_target_directory",
        return_value=str(tmp_path),
    ):
        result = await planner.execute(
            action="execute_sandbox_code",
            params={
                "prompt": f"Write script in project workspace {str(tmp_path)}"
            },
        )

    assert "Sandbox execution verified." in result
    assert "Sandbox Execution Complete." in result


@pytest.mark.asyncio
async def test_execute_sandbox_code_empty_prompt(planner):
    """Test dynamic execution request with missing prompt."""
    result = await planner.execute(action="execute_sandbox_code", params={})
    assert (
        "Error: A 'prompt' or 'intent' parameter is required to execute sandbox code."
        in result
    )


# ============================================================================
# 6. UNKNOWN ACTION & ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unknown_action_raises_value_error(planner):
    """Verify that an unsupported action raises a ValueError."""
    with pytest.raises(ValueError, match="Unknown Planner action"):
        # Bypass fallback payload validation by providing explicit unknown action
        with patch(
            "charon.agents.planner.agent.PlannerPayload.model_validate"
        ) as mock_validate:
            mock_payload = MagicMock()
            mock_payload.action = "invalid_action_xyz"
            mock_validate.return_value = mock_payload

            await planner.execute(action="invalid_action_xyz")
