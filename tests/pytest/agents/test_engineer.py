"""Unit tests for Charon's Engineer agent and code tools."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Tools imports
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess

# Agent and handler imports
from charon.agents.engineer import (
    TheEngineer,
    handle_execute_sandbox_code,
    handle_generate_script_only,
    handle_run_existing_script,
    handle_solve_edge_case,
)
from charon.intent import EngineerPayload


# ============================================================================
# 1. Tests for Stateless Tools (`charon/tools/code.py`)
# ============================================================================

class TestCodeTools:
    """Tests for AST auditing and subshell execution tools."""

    def test_audit_written_artifacts_no_writes(self, tmp_path):
        code = "x = 1 + 1\nprint(x)"
        ok, msg = audit_written_artifacts(code, cwd=str(tmp_path))
        assert ok is True
        assert "No disk write calls detected" in msg

    def test_audit_written_artifacts_verified_writes(self, tmp_path):
        target_file = tmp_path / "output.txt"
        target_file.write_text("hello")

        code = 'with open("output.txt", "w") as f:\n    f.write("hello")'
        ok, msg = audit_written_artifacts(code, cwd=str(tmp_path))
        assert ok is True
        assert "1 file artifact(s) created" in msg

    def test_audit_written_artifacts_missing_file_warning(self, tmp_path):
        code = 'with open("non_existent.txt", "w") as f:\n    f.write("hello")'
        ok, msg = audit_written_artifacts(code, cwd=str(tmp_path))
        assert ok is False
        assert "AST Disk Audit Warning" in msg
        assert "non_existent.txt" in msg

    def test_audit_written_artifacts_ast_syntax_error(self, tmp_path):
        invalid_code = "def invalid_syntax(:"
        ok, msg = audit_written_artifacts(invalid_code, cwd=str(tmp_path))
        assert ok is False
        assert "AST Parse Error" in msg

    @pytest.mark.asyncio
    async def test_run_script_in_subprocess_success(self, tmp_path):
        code = 'print("Hello from subprocess")'
        output, success = await run_script_in_subprocess(code, cwd=str(tmp_path))
        assert success is True
        assert "Hello from subprocess" in output

    @pytest.mark.asyncio
    async def test_run_script_in_subprocess_failure(self, tmp_path):
        code = 'raise ValueError("Intentional execution error")'
        output, success = await run_script_in_subprocess(code, cwd=str(tmp_path))
        assert success is False
        assert "ValueError: Intentional execution error" in output

    @pytest.mark.asyncio
    async def test_run_script_in_subprocess_timeout(self, tmp_path):
        code = "import time\ntime.sleep(5)"
        output, success = await run_script_in_subprocess(
            code, cwd=str(tmp_path), timeout=0.1
        )
        assert success is False
        assert "TimeoutError" in output


# ============================================================================
# 2. Tests for Domain Handlers (`charon/agents/engineer/`)
# ============================================================================

class TestEngineerHandlers:
    """Tests for Engineer domain handler functions."""

    @pytest.mark.asyncio
    async def test_handle_generate_script_only(self):
        mock_client = AsyncMock()
        mock_client.generate.return_value = {
            "response": "```python\nprint('Generated')\n```"
        }

        result = await handle_generate_script_only(
            client=mock_client,
            model_name="llama3.1",
            raw_prompt="Write a print statement",
        )

        assert "print('Generated')" in result
        mock_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_execute_sandbox_code_success(self, tmp_path):
        payload = EngineerPayload(
            action="execute_sandbox_code",
            prompt="print('Sandbox test')",
            target_dir=str(tmp_path),
        )

        result = await handle_execute_sandbox_code(
            python_cmd="python",
            payload=payload,
            params={"code": "print('Sandbox test')"},
        )

        assert "[SUCCESS]" in result
        assert "Sandbox test" in result

    @pytest.mark.asyncio
    async def test_handle_run_existing_script(self, tmp_path):
        script_file = tmp_path / "test_script.py"
        script_file.write_text("print('Existing script executed')")

        payload = EngineerPayload(
            action="run_existing_script",
            script_path=str(script_file),
            target_dir=str(tmp_path),
        )

        result = await handle_run_existing_script(
            python_cmd="python",
            payload=payload,
        )

        assert "(Success)" in result
        assert "Existing script executed" in result

    @pytest.mark.asyncio
    async def test_handle_solve_edge_case_self_healing(self, tmp_path):
        mock_client = AsyncMock()
        # Pass 1 returns broken code, Pass 2 returns working code
        mock_client.generate.side_effect = [
            {"response": "```python\nraise RuntimeError('Bug on pass 1')\n```"},
            {"response": "```python\nprint('Pass 2 success')\n```"},
        ]

        payload = EngineerPayload(
            action="solve_edge_case",
            problem="Fix edge case",
            max_attempts=3,
            target_dir=str(tmp_path),
        )

        result = await handle_solve_edge_case(
            client=mock_client,
            model_name="llama3.1",
            python_cmd="python",
            payload=payload,
        )

        assert "Edge Case Resolved (Attempt 2/3)" in result
        assert "Pass 2 success" in result
        assert mock_client.generate.call_count == 2


# ============================================================================
# 3. Tests for Primary Agent Interface (`TheEngineer`)
# ============================================================================

class TestTheEngineerAgent:
    """Tests for main TheEngineer agent class entry point."""

    @pytest.fixture
    def engineer(self):
        with patch("charon.agents.engineer.agent.ollama.AsyncClient"):
            return TheEngineer(model_name="llama3.1")

    @pytest.mark.asyncio
    async def test_execute_routing_generate_script(self, engineer):
        engineer.client.generate = AsyncMock(
            return_value={"response": "```python\n# Draft\n```"}
        )

        res = await engineer.execute(
            action="generate_script",
            parameters={"prompt": "Draft a script"},
        )
        assert "# Draft" in res

    @pytest.mark.asyncio
    async def test_execute_routing_sandbox(self, engineer, tmp_path):
        res = await engineer.execute(
            action="execute_sandbox_code",
            parameters={
                "code": "print('Agent Sandbox')",
                "target_dir": str(tmp_path),
            },
        )
        assert "[SUCCESS]" in res
        assert "Agent Sandbox" in res

    @pytest.mark.asyncio
    async def test_execute_routing_fallback_action(self, engineer, tmp_path):
        engineer.client.generate = AsyncMock(
            return_value={"response": "```python\nprint('Fallback')\n```"}
        )

        res = await engineer.execute(
            action="unknown_action",
            parameters={"problem": "Do something", "target_dir": str(tmp_path)},
        )
        assert "Edge Case Resolved" in res or "Failed to Resolve" in res
