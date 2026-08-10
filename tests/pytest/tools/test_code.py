"""Tests for AST code auditing, workspace path extraction, and subshell sandbox execution."""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from charon.sdk import HardwareTelemetry, CharonClientNode
from charon.tools.code import (
    audit_written_artifacts,
    extract_target_directory,
    run_script_in_subprocess,
)


# ==========================================
# Tests for extract_target_directory
# ==========================================


class TestExtractTargetDirectory:

    def test_extract_exact_absolute_path(self, tmp_path: Path):
        target = tmp_path / "workspace"
        target.mkdir()
        prompt = f"Please update the code located in {target} for me."

        result = extract_target_directory(prompt)
        assert result == str(target.resolve())

    def test_extract_quoted_absolute_path(self, tmp_path: Path):
        """Covers quoted absolute paths in prompt."""
        target = tmp_path / "quoted_workspace"
        target.mkdir()
        prompt = f"Check the directory at '{target}' right now."

        result = extract_target_directory(prompt)
        assert result == str(target.resolve())

    def test_extract_existing_file_absolute_path(self, tmp_path: Path):
        """Covers branch where absolute path in prompt is an existing file on disk."""
        target_file = tmp_path / "script.py"
        target_file.touch()
        prompt = f"Please analyze the file at {target_file} for bugs."

        result = extract_target_directory(prompt)
        assert result == str(tmp_path.resolve())

    def test_extract_parent_fallback_path(self, tmp_path: Path):
        target = tmp_path / "workspace"
        target.mkdir()
        prompt = f"I have a file at {target}/file.py"

        result = extract_target_directory(prompt)
        assert result == str(target.resolve())

    def test_extract_abs_path_nonexistent_loop_continue(self):
        """Covers branch where abs path and its parent do not exist."""
        prompt = (
            "Check /nonexistent_folder_xyz123/sub_dir_456/file.py please"
        )
        result = extract_target_directory(prompt)
        assert result is None

    @patch("pathlib.Path.is_dir")
    @patch("pathlib.Path.resolve")
    def test_extract_windows_path(self, mock_resolve, mock_is_dir):
        """Covers Windows drive paths (e.g. C:\\... or D:/...)."""
        mock_is_dir.side_effect = lambda: True
        mock_resolve.return_value = Path("C:/Users/Developer/workspace")

        prompt = r"Check C:\Users\Developer\workspace for errors."
        result = extract_target_directory(prompt)
        assert result == str(Path("C:/Users/Developer/workspace"))

    def test_extract_base_rule_matches_existing_dir(self, tmp_path: Path):
        base_dir = tmp_path / "base_folder"
        base_dir.mkdir()

        prompt = f"Look into {base_dir} directory"
        result = extract_target_directory(prompt)
        assert result == str(base_dir.resolve())

    def test_extract_tilde_path_expansion(self, tmp_path: Path):
        """Covers user directory expansion (~/...) in base rule matching."""
        d = tmp_path / "tilde_workspace"
        d.mkdir()

        with patch("os.path.expanduser", return_value=str(d)), patch(
            "pathlib.Path.expanduser", return_value=d
        ):
            prompt = "Look at ~/tilde_workspace for logs"
            result = extract_target_directory(prompt)
            assert result == str(d.resolve())

    @patch("charon.tools.code.resolve_project_path")
    def test_extract_project_keyword_resolved(
        self, mock_resolve, tmp_path: Path
    ):
        target = tmp_path / "my_bot"
        target.mkdir()
        mock_resolve.return_value = target

        prompt = "Add a feature to project my_bot"
        result = extract_target_directory(prompt)

        mock_resolve.assert_called_once_with("my_bot")
        assert result == str(target.resolve())

    @patch(
        "charon.tools.code.resolve_project_path",
        side_effect=Exception("Resolution failed"),
    )
    def test_extract_project_resolution_exception_handling(
        self, mock_resolve
    ):
        """Covers exception raised during resolve_project_path."""
        prompt = "Working on project bad_proj"
        result = extract_target_directory(prompt)
        assert result is None

    @patch(
        "charon.tools.code.resolve_project_path",
        side_effect=RuntimeError("Resolution failed"),
    )
    def test_extract_project_resolution_exception_fallback(
        self, mock_resolve, tmp_path: Path
    ):
        """Covers project path resolution failing but falling back to base directories."""
        base_dir = tmp_path / "projects"
        base_dir.mkdir()
        target_proj = base_dir / "my_project"
        target_proj.mkdir()

        with patch("charon.tools.code.PROJECTS_DIR", base_dir):
            prompt = "Check repo my_project"
            result = extract_target_directory(prompt)
            assert result == str(target_proj.resolve())

    @patch("charon.tools.code.resolve_project_path")
    def test_extract_project_keyword_fallback_to_base_dirs(
        self, mock_resolve, tmp_path: Path
    ):
        """Covers fallback to checking base directories when resolve_project_path returns non-existent path."""
        base_dir = tmp_path / "projects_base"
        base_dir.mkdir()

        proj_dir = base_dir / "custom_bot"
        proj_dir.mkdir()

        non_existent = tmp_path / "non_existent_project"
        mock_resolve.return_value = non_existent

        prompt = "Inspect repo custom_bot"
        with patch("charon.tools.code.PROJECTS_DIR", base_dir):
            result = extract_target_directory(prompt)

        assert result == str(proj_dir.resolve())

    def test_extract_folder_name_in_projects_dir(self, tmp_path: Path):
        """Covers prompt referencing folder name directly inside PROJECTS_DIR."""
        proj_dir = tmp_path / "my_secret_repo"
        proj_dir.mkdir()

        (tmp_path / "README.md").touch()

        with patch("charon.tools.code.PROJECTS_DIR", tmp_path):
            prompt = "Please look at repo my_secret_repo and fix the bugs"
            result = extract_target_directory(prompt)
            assert result == str(proj_dir.resolve())

    def test_extract_projects_dir_loop_skips_non_matching_dirs(
        self, tmp_path: Path
    ):
        """Covers directory iteration in PROJECTS_DIR where subdirectories exist but none match prompt words."""
        (tmp_path / "other_project_a").mkdir()
        (tmp_path / "other_project_b").mkdir()

        with patch("charon.tools.code.PROJECTS_DIR", tmp_path):
            prompt = "Please run tests for unrelated_thing"
            result = extract_target_directory(prompt)
            assert result is None

    def test_extract_projects_dir_contains_files_only(self, tmp_path: Path):
        """Explicitly tests PROJECTS_DIR containing non-directory files."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.py").touch()

        with patch("charon.tools.code.PROJECTS_DIR", tmp_path):
            prompt = "Please check project file1"
            result = extract_target_directory(prompt)
            assert result is None

    def test_extract_projects_dir_does_not_exist(self, tmp_path: Path):
        """Covers branch where PROJECTS_DIR does not exist on disk."""
        non_existent_projects = tmp_path / "no_projects_here"
        with patch("charon.tools.code.PROJECTS_DIR", non_existent_projects):
            prompt = "Please look at repo my_secret_repo"
            result = extract_target_directory(prompt)
            assert result is None

    def test_extract_projects_dir_branch(self, tmp_path: Path):
        with patch("charon.tools.code.PROJECTS_DIR", tmp_path):
            prompt = "Quick python task"
            result = extract_target_directory(prompt)
            assert result is None

    def test_extract_target_directory_default_projects_appended(
        self, tmp_path: Path
    ):
        """Covers appending default_projects directory when base_rule_matches is empty."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        with patch("charon.tools.code.PROJECTS_DIR", projects_dir):
            prompt = "Where is the repo my_project?"
            result = extract_target_directory(prompt)
            assert result is None

    def test_extract_no_match(self):
        prompt = "Just write a quick python script for me."
        result = extract_target_directory(prompt)
        assert result is None


# ==========================================
# Tests for audit_written_artifacts
# ==========================================


class TestAuditWrittenArtifacts:

    def test_audit_syntax_error(self, tmp_path: Path):
        code = "def oops(:"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert not success
        assert "AST Parse Error" in msg

    def test_audit_no_writes_detected(self, tmp_path: Path):
        code = "print('Hello, world!')\nx = 1 + 1"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success
        assert "No disk write calls detected" in msg

    def test_audit_open_read_mode(self, tmp_path: Path):
        code = "with open('input.txt', 'r') as f:\n    data = f.read()"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success
        assert "No disk write calls detected" in msg

    def test_audit_open_keyword_read_mode(self, tmp_path: Path):
        code = "with open('input.txt', mode='r') as f:\n    data = f.read()"
        (tmp_path / "input.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_open_write_success(self, tmp_path: Path):
        code = """
with open('output.txt', 'w') as f:
    f.write('data')
"""
        (tmp_path / "output.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_open_non_write_mode_branch(self, tmp_path: Path):
        """Covers branch for open call with non-write mode (e.g., 'r')."""
        code = "open('input.txt', mode='rb').read()"
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "No disk write calls detected" in msg

    def test_audit_open_non_constant_args_branch(self, tmp_path: Path):
        """Covers branch where open call mode argument is complex/unknown variable."""
        code = "open('input.txt', get_mode())"
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_tuple_unpacking_assignment(self, tmp_path: Path):
        """Covers AST tuple/list target assignments (e.g. x, y = a, b)."""
        code = """
a, b = "file.txt", "w"
with open(a, b) as f:
    f.write("hello")
"""
        (tmp_path / "file.txt").touch()
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_non_string_variable_assignment(self, tmp_path: Path):
        """Covers AST assignments to non-string constants (e.g. x = 100)."""
        code = """
x = 100
a, b = 1, 2
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_tracked_string_variable_open(self, tmp_path: Path):
        """Covers open(var, 'w') where var = 'results.csv' is tracked by AST."""
        output_file = tmp_path / "results.csv"
        output_file.write_text("a,b,c")

        code = (
            'filename = "results.csv"\n'
            'with open(filename, "a") as f:\n'
            '    f.write("1,2,3")'
        )
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_tracked_path_variable_write_text(self, tmp_path: Path):
        """Covers p.write_text() where p = Path('report.md') is tracked by AST."""
        output_file = tmp_path / "report.md"
        output_file.write_text("# Report")

        code = (
            "from pathlib import Path\n"
            'target = Path("report.md")\n'
            'target.write_text("Updated content")'
        )
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_inline_path_str_var_write_text(self, tmp_path: Path):
        """Covers inline Path(str_var).write_text() where str_var is a tracked variable name."""
        output_file = tmp_path / "inline_out.txt"
        output_file.touch()

        code = (
            "from pathlib import Path\n"
            'fn = "inline_out.txt"\n'
            'Path(fn).write_text("hello world")'
        )
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_tracked_str_to_path_variable_write_bytes(
        self, tmp_path: Path
    ):
        """Covers target = Path(var) where var = 'data.bin'."""
        output_file = tmp_path / "data.bin"
        output_file.write_bytes(b"\x00\x01")

        code = (
            "from pathlib import Path\n"
            'name = "data.bin"\n'
            "file_path = Path(name)\n"
            'file_path.write_bytes(b"\\x00")'
        )
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_open_append_mode(self, tmp_path: Path):
        code = "open('log.txt', mode='a').write('appended')"
        (tmp_path / "log.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_open_exclusive_mode(self, tmp_path: Path):
        code = "open('new.txt', 'x').write('data')"
        (tmp_path / "new.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_open_read_write_mode(self, tmp_path: Path):
        code = "open('rw.txt', 'r+').write('data')"
        (tmp_path / "rw.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_open_keyword_non_constant_mode(self, tmp_path: Path):
        code = "m = 'w'\nopen('log.txt', mode=m).write('data')"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success

    def test_audit_open_integer_fd_or_non_string(self, tmp_path: Path):
        """Covers open() called with an integer file descriptor or numeric constant."""
        code = "open(1, mode='w').write('data')"
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_open_no_args(self, tmp_path: Path):
        code = "open()"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success

    def test_audit_open_keyword_file_arg(self, tmp_path: Path):
        code = "open(file='out.txt', mode='w').write('data')"
        (tmp_path / "out.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_path_open_read_mode(self, tmp_path: Path):
        code = "from pathlib import Path\nPath('in.txt').open('r').read()"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success
        assert "No disk write calls detected" in msg

    def test_audit_path_open_no_args(self, tmp_path: Path):
        code = "from pathlib import Path\nPath('in.txt').open()"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success
        assert "No disk write calls detected" in msg

    def test_audit_path_open_keyword_read_mode(self, tmp_path: Path):
        code = "from pathlib import Path\nPath('in.txt').open(mode='r')"
        (tmp_path / "in.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_path_open_positional_mode(self, tmp_path: Path):
        code = "from pathlib import Path\nPath('out.txt').open('w').write('data')"
        (tmp_path / "out.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_path_open_keyword_mode(self, tmp_path: Path):
        code = (
            "from pathlib import Path\n"
            "Path('out.txt').open(mode='w').write('data')"
        )
        (tmp_path / "out.txt").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_path_open_non_constant_mode(self, tmp_path: Path):
        code = "from pathlib import Path\nm = 'w'\nPath('in.txt').open(mode=m)"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success

    def test_audit_path_open_non_constant_positional_mode(
        self, tmp_path: Path
    ):
        code = "from pathlib import Path\nm = 'w'\nPath('in.txt').open(m)"
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert success

    def test_audit_path_write_bytes(self, tmp_path: Path):
        code = (
            "from pathlib import Path\nPath('out.bin').write_bytes(b'data')"
        )
        (tmp_path / "out.bin").touch()

        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "1 file artifact(s) created" in msg

    def test_audit_path_call_non_constant_non_name_arg(self, tmp_path: Path):
        """Covers Path(12345).write_text(...) where arg0 is Constant but not a string."""
        code = """
from pathlib import Path
Path(12345).write_text("hello")
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success
        assert "No disk write calls detected" in msg

    def test_audit_path_invalid_arg_types(self, tmp_path: Path):
        """Covers Path(...) initialized with non-string/invalid AST constant node."""
        code = """
from pathlib import Path
Path(12345).write_text("data")
Path().write_bytes(b"data")
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_path_write_missing_file(self, tmp_path: Path):
        code = """
from pathlib import Path
Path('data.json').write_text('{}')
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert not success
        assert "expected output file(s) were missing" in msg
        assert "data.json" in msg

    def test_audit_path_open_missing_file(self, tmp_path: Path):
        """Covers auditing missing file via Path(...).open('w')"""
        code = """
from pathlib import Path
with Path('missing_open.txt').open('w') as f:
    f.write('{}')
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))

        assert not success
        assert "expected output file(s) were missing" in msg
        assert "missing_open.txt" in msg

    def test_audit_mixed_existing_and_missing_files_branch(
        self, tmp_path: Path
    ):
        """Covers branch where both created files and missing files exist."""
        (tmp_path / "exists.txt").touch()
        code = """
with open('exists.txt', 'w') as f:
    f.write('ok')
with open('missing.txt', 'w') as f:
    f.write('missing')
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert not success
        assert "1 file artifact(s) created" in msg
        assert "missing.txt" in msg

    def test_audit_non_path_attribute_calls(self, tmp_path: Path):
        """Covers branch where method open/write_text/write_bytes is called on generic objects."""
        code = """
var = get_handle()
var.write_text('data')
var.open('w')
var.write_bytes(b'data')
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success

    def test_audit_non_target_attributes_and_calls(self, tmp_path: Path):
        code = """
get_path().write_text('data')
Path(variable_name).write_text('data')
Path().write_text('data')
'string'.upper()
"""
        success, msg = audit_written_artifacts(code, str(tmp_path))
        assert success


# ==========================================
# Tests for run_script_in_subprocess
# ==========================================


class TestRunScriptInSubprocess:

    @pytest.mark.asyncio
    async def test_run_script_success(self, tmp_path: Path):
        code = "print('Execution successful')"
        output, success = await run_script_in_subprocess(code, str(tmp_path))

        assert success is True
        assert "Execution successful" in output

    @pytest.mark.asyncio
    async def test_run_script_non_existent_cwd(self):
        code = "print('Non existent CWD run')"
        non_existent_cwd = "/nonexistent_workspace_dir_123_abc"

        output, success = await run_script_in_subprocess(
            code, non_existent_cwd
        )
        assert success is True
        assert "Non existent CWD run" in output

    @pytest.mark.asyncio
    async def test_run_script_failure_exit_code(self, tmp_path: Path):
        code = """
import sys
print('About to fail')
sys.exit(1)
"""
        output, success = await run_script_in_subprocess(code, str(tmp_path))

        assert success is False
        assert "About to fail" in output

    @pytest.mark.asyncio
    async def test_run_script_custom_environment_variables(
        self, tmp_path: Path
    ):
        """Covers custom env dictionary injection into subprocess execution."""
        code = 'import os\nprint(os.environ.get("TEST_KEY", ""))'
        env = {**os.environ, "TEST_KEY": "CHARON_PASSED"}

        output, success = await run_script_in_subprocess(
            code, str(tmp_path), env=env
        )
        assert success is True
        assert output == "CHARON_PASSED"

    @pytest.mark.asyncio
    async def test_run_script_timeout(self, tmp_path: Path):
        code = """
import time
time.sleep(2.0)
"""
        output, success = await run_script_in_subprocess(
            code, str(tmp_path), timeout=0.1
        )

        assert success is False
        assert "Execution TimeoutError" in output
        assert "0.1" in output

    @pytest.mark.asyncio
    async def test_run_script_timeout_kill_exception(self, tmp_path: Path):
        code = "import time\ntime.sleep(2.0)"

        mock_process = AsyncMock()
        mock_process.stdout = None
        mock_process.stderr = None
        mock_process.kill = MagicMock(
            side_effect=RuntimeError("Process already terminated")
        )
        mock_process.wait = AsyncMock()

        async def dummy_wait_for(fut, timeout):
            raise asyncio.TimeoutError()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=dummy_wait_for):
                output, success = await run_script_in_subprocess(
                    code, str(tmp_path), timeout=0.01
                )

                assert success is False
                assert "Execution TimeoutError" in output
                mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_script_stdout_only(self, tmp_path: Path):
        """Covers stream task creation when stderr is None."""
        mock_stream = AsyncMock()
        mock_stream.readline = AsyncMock(
            side_effect=[b"stdout message\n", b""]
        )

        mock_process = AsyncMock()
        mock_process.stdout = mock_stream
        mock_process.stderr = None
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is True
            assert "stdout message" in output

    @pytest.mark.asyncio
    async def test_run_script_stderr_only(self, tmp_path: Path):
        """Covers stream task creation when stdout is None."""
        mock_stream = AsyncMock()
        mock_stream.readline = AsyncMock(
            side_effect=[b"stderr message\n", b""]
        )

        mock_process = AsyncMock()
        mock_process.stdout = None
        mock_process.stderr = mock_stream
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is True
            assert "stderr message" in output

    @pytest.mark.asyncio
    async def test_run_script_stderr_equals_stdout(self, tmp_path: Path):
        """Covers branch where process.stderr == process.stdout in _run_and_read."""
        mock_stream = AsyncMock()
        mock_stream.readline = AsyncMock(
            side_effect=[b"merged output\n", b""]
        )

        mock_process = AsyncMock()
        mock_process.stdout = mock_stream
        mock_process.stderr = mock_stream
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is True
            assert "merged output" in output

    @pytest.mark.asyncio
    async def test_run_script_stdout_and_stderr_none(self, tmp_path: Path):
        mock_process = AsyncMock()
        mock_process.stdout = None
        mock_process.stderr = None
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is True
            assert output == ""

    @pytest.mark.asyncio
    async def test_run_script_returncode_none_fallback(self, tmp_path: Path):
        """Covers fallback branch when process returncode is None."""
        mock_process = AsyncMock()
        mock_process.stdout = None
        mock_process.stderr = None
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=None)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is False

    @pytest.mark.asyncio
    async def test_run_script_generic_exception(self, tmp_path: Path):
        """Covers generic Exception handling during process execution."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("Failed to spawn process"),
        ):
            output, success = await run_script_in_subprocess(
                "print('test')", str(tmp_path)
            )
            assert success is False
            assert "Failed to spawn process" in output or "Execution Error" in output

    @pytest.mark.asyncio
    async def test_run_script_stream_callback(self, tmp_path: Path):
        code = """
import sys
sys.stdout.write('chunk 1\\n')
sys.stdout.flush()
sys.stdout.write('chunk 2\\n')
"""
        captured_chunks = []

        def callback(chunk: str):
            captured_chunks.append(chunk)

        output, success = await run_script_in_subprocess(
            code, str(tmp_path), stream_callback=callback
        )

        assert success is True
        assert "chunk 1\nchunk 2" in output
        assert len(captured_chunks) > 0
        assert "".join(captured_chunks) == "chunk 1\nchunk 2\n"

    @pytest.mark.asyncio
    async def test_run_script_stream_callback_exception_resilience(
        self, tmp_path: Path
    ):
        """Covers stream_callback throwing an unhandled exception during log reading."""
        code = "print('streaming line')"

        def failing_callback(chunk: str):
            raise RuntimeError("Callback crashed")

        output, success = await run_script_in_subprocess(
            code, str(tmp_path), stream_callback=failing_callback
        )
        assert success is True
        assert "streaming line" in output

    @pytest.mark.asyncio
    async def test_run_script_finally_os_remove_error(self, tmp_path: Path):
        """Covers OSError handling during subprocess cleanup."""
        code = "print('Cleanup test')"

        with patch("os.remove", side_effect=OSError("Permission denied")):
            output, success = await run_script_in_subprocess(
                code, str(tmp_path)
            )
            assert success is True
            assert "Cleanup test" in output

    def test_audit_open_untracked_filename(self):
        """Covers Lines 108-111: open() with dynamic/untracked filename arguments."""

        # Positional arg is a function call
        code1 = "open(get_filename(), 'w')"
        valid, _ = audit_written_artifacts(code1, "/tmp")
        assert valid is True

        # Missing positional arguments entirely
        code2 = "open(file='test.txt', mode='w')"
        valid, _ = audit_written_artifacts(code2, "/tmp")
        assert valid is True

    def test_audit_path_untracked_arguments(self):
        """Covers Lines 149-163: Path() with untracked args and dynamic modes."""

        # Path argument is a function call
        code1 = "Path(get_filename()).write_text('data')"
        valid, _ = audit_written_artifacts(code1, "/tmp")
        assert valid is True

        # Path.open with a dynamic positional mode
        code2 = "Path('test.txt').open(get_mode())"
        valid, _ = audit_written_artifacts(code2, "/tmp")
        assert valid is True

        # Path.open with a dynamic keyword mode
        code3 = "Path('test.txt').open(mode=get_mode())"
        valid, _ = audit_written_artifacts(code3, "/tmp")
        assert valid is True

        # Path without arguments
        code4 = "Path().write_text('data')"
        valid, _ = audit_written_artifacts(code4, "/tmp")
        assert valid is True

    @pytest.mark.asyncio
    async def test_run_script_stream_callback_exception(self):
        """Covers Line 246: Exception raised within stream_callback."""

        def buggy_callback(chunk: str):
            raise ValueError("Callback explicitly failed for coverage")

        code = "print('Trigger callback')"

        # Execution should still succeed despite the callback throwing an exception
        output, success = await run_script_in_subprocess(
            code,
            cwd=".",
            stream_callback=buggy_callback
        )

        assert success is True
        assert "Trigger callback" in output

class TestSDKFinalCoverage:
    """Targeted tests to cover remaining missed lines/branches in charon/sdk.py."""

    def test_detect_usb_devices_nonzero_exit_branch(self):
        """Covers branch 129->137: lsusb executable exists but returns non-zero code."""
        mock_res = MagicMock(returncode=1, stdout="")
        with patch("shutil.which", return_value="/usr/bin/lsusb"), \
                patch("subprocess.run", return_value=mock_res):
            assert HardwareTelemetry.detect_usb_devices() == []

    def test_collect_cpu_count_none_fallback_lines(self):
        """Covers lines 155-156: Fallback when os.cpu_count() returns None/fails."""
        with patch("os.cpu_count", return_value=None):
            telemetry = HardwareTelemetry.collect()
            # Ensures fallback logic (e.g., cpu_cores = 1) is executed
            assert telemetry["cpu_cores"] == 1

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_unregistered_event_branch(self):
        """Covers branch 306->313: WS event dispatched with no matching listener."""
        node = CharonClientNode(client_id="unregistered_node", auto_discover_hardware=False)

        # Dispatch an event type that has no listener attached
        payload = json.dumps({"event_type": "unknown_unregistered_event", "data": {"key": "val"}})

        # Should execute safely without raising or invoking handlers
        await node._dispatch_ws_message(payload)


