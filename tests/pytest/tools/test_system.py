import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Adjust import path to match your project structure
from charon.tools import system


# ==========================================
# Fixtures & Mocks
# ==========================================

@pytest.fixture
def mock_psutil():
    """Mocks standard psutil responses."""
    with patch("charon.tools.system.psutil") as mock_ps:
        mock_ps.cpu_percent.return_value = 15.5

        mock_vm = MagicMock()
        mock_vm.percent = 45.0
        mock_vm.used = 4 * 1024 ** 3  # 4 GB
        mock_vm.total = 16 * 1024 ** 3  # 16 GB
        mock_vm.available = 12 * 1024 ** 3  # 12 GB
        mock_ps.virtual_memory.return_value = mock_vm

        mock_disk = MagicMock()
        mock_disk.percent = 60.0
        mock_disk.free = 100 * 1024 ** 3  # 100 GB
        mock_ps.disk_usage.return_value = mock_disk

        mock_proc = MagicMock()
        mock_mem_info = MagicMock()
        mock_mem_info.rss = 150 * 1024 ** 2  # 150 MB
        mock_proc.memory_info.return_value = mock_mem_info
        mock_proc.cpu_percent.return_value = 2.5
        mock_ps.Process.return_value = mock_proc

        yield mock_ps


class MockAsyncProcess:
    """A helper to simulate asyncio subprocesses."""

    def __init__(self, stdout_lines, returncode=0, sleep_time=0.0):
        self.returncode = returncode
        self.sleep_time = sleep_time
        self.killed = False

        class MockStdout:
            def __init__(self, lines, sleep_time):
                self.lines = lines
                self.sleep_time = sleep_time
                self.index = 0

            async def readline(self):
                if self.sleep_time > 0:
                    await asyncio.sleep(self.sleep_time)
                if self.index < len(self.lines):
                    line = self.lines[self.index]
                    self.index += 1
                    return line
                return b""

        self.stdout = MockStdout(stdout_lines, sleep_time)

    async def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True


# ==========================================
# Module Import & Initialization Tests
# ==========================================

def test_psutil_import_error_on_module_load():
    """Triggers lines 15-16 by simulating psutil missing during module import."""
    with patch.dict(sys.modules, {"psutil": None}):
        importlib.reload(system)
        assert system.PSUTIL_AVAILABLE is False

    # Restore module state for remaining tests
    importlib.reload(system)


# ==========================================
# Tests for get_system_info
# ==========================================

def test_get_system_info_with_psutil(mock_psutil):
    with patch("charon.tools.system.platform.system", return_value="Linux"), \
            patch("charon.tools.system.platform.release", return_value="5.15.0"), \
            patch("charon.tools.system.platform.architecture", return_value=("64bit", "ELF")), \
            patch("charon.tools.system.platform.node", return_value="test-node"), \
            patch("charon.tools.system.platform.processor", return_value="x86_64"), \
            patch("charon.tools.system.sys.version", "3.11.2 (main)"), \
            patch("charon.tools.system.PSUTIL_AVAILABLE", True):
        info = system.get_system_info()

    assert "OS: Linux 5.15.0 (64bit)" in info
    assert "Hostname: test-node" in info
    assert "Processor: x86_64" in info
    assert "CPU Load: 15.5%" in info
    assert "RAM Usage: 45.0%" in info
    assert "Disk Usage: 60.0% (100GB free)" in info


def test_get_system_info_without_psutil():
    with patch("charon.tools.system.PSUTIL_AVAILABLE", False):
        info = system.get_system_info()

    assert "psutil: Not installed" in info
    assert "CPU Load" not in info


def test_get_system_info_processor_fallback():
    """Test fallback when platform.processor() returns an empty string."""
    with patch("charon.tools.system.platform.processor", return_value=""), \
         patch("charon.tools.system.PSUTIL_AVAILABLE", False):
        info = system.get_system_info()
        assert "Processor: Generic/System Native" in info


# ==========================================
# Tests for get_system_telemetry
# ==========================================

@patch("charon.tools.system.shutil.disk_usage")
def test_get_system_telemetry_with_psutil(mock_disk_usage, mock_psutil):
    mock_disk_usage.return_value = (500 * 1024 ** 3, 100 * 1024 ** 3, 400 * 1024 ** 3)  # total, used, free

    with patch("charon.tools.system.PSUTIL_AVAILABLE", True):
        telemetry = system.get_system_telemetry()

    assert "telemetry" in telemetry
    assert telemetry["telemetry"]["cpu_percent"] == 15.5
    assert telemetry["telemetry"]["ram_available_mb"] == 12288.0
    assert telemetry["telemetry"]["daemon_ram_rss_mb"] == 150.0

    assert "disk_usage" in telemetry
    assert telemetry["disk_usage"]["total_gb"] == 500.0
    assert telemetry["disk_usage"]["free_gb"] == 400.0
    assert telemetry["disk_usage"]["percent_used"] == 20.0


@patch("charon.tools.system.shutil.disk_usage")
def test_get_system_telemetry_without_psutil(mock_disk_usage):
    mock_disk_usage.return_value = (500 * 1024 ** 3, 100 * 1024 ** 3, 400 * 1024 ** 3)

    with patch("charon.tools.system.PSUTIL_AVAILABLE", False):
        telemetry = system.get_system_telemetry()

    assert telemetry["telemetry"] == {"psutil": "not_installed"}
    assert "disk_usage" in telemetry


@patch("charon.tools.system.shutil.disk_usage", side_effect=PermissionError("Access Denied"))
def test_get_system_telemetry_disk_error(mock_disk_usage, mock_psutil):
    with patch("charon.tools.system.PSUTIL_AVAILABLE", True):
        telemetry = system.get_system_telemetry()

    assert "disk_usage_error" in telemetry
    assert "Access Denied" in telemetry["disk_usage_error"]
    assert "disk_usage" not in telemetry


# ==========================================
# Tests for execute_shell_command (Async)
# ==========================================

@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_success(mock_subprocess):
    mock_proc = MockAsyncProcess(stdout_lines=[b"Line 1\n", b"Line 2\n"], returncode=0)
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("echo test")

    assert "Command Execution Status: Success" in result
    assert "Line 1\nLine 2" in result


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_failure(mock_subprocess):
    mock_proc = MockAsyncProcess(stdout_lines=[b"Error occurred\n"], returncode=1)
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("ls /nonexistent")

    assert "Failed (exit code 1)" in result
    assert "Error occurred" in result


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_timeout(mock_subprocess):
    # Process sleeps for 1 second per read, but our timeout is 0.1s
    mock_proc = MockAsyncProcess(stdout_lines=[b"Will timeout\n"], sleep_time=1.0)
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("sleep 5", timeout=0.1)

    assert "Failed (Execution timed out after 0.1s)" in result
    assert "Process killed due to timeout." in result
    assert mock_proc.killed is True


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_with_stream_callback(mock_subprocess):
    mock_proc = MockAsyncProcess(stdout_lines=[b"Chunk A\n", b"Chunk B\n"])
    mock_subprocess.return_value = mock_proc

    callback_mock = MagicMock()

    await system.execute_shell_command("echo test", stream_callback=callback_mock)

    assert callback_mock.call_count == 2
    callback_mock.assert_any_call("Chunk A\n")
    callback_mock.assert_any_call("Chunk B\n")


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_no_output(mock_subprocess):
    """Test command execution returning no stdout output."""
    mock_proc = MockAsyncProcess(stdout_lines=[], returncode=0)
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("true")

    assert "Command Execution Status: Success" in result
    assert "(Command executed with no terminal output)" in result


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_stdout_none(mock_subprocess):
    """Test early return in _read_stream when process.stdout is None."""
    mock_proc = MockAsyncProcess(stdout_lines=[], returncode=0)
    mock_proc.stdout = None
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("true")

    assert "Command Execution Status: Success" in result
    assert "(Command executed with no terminal output)" in result


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell")
async def test_execute_shell_command_timeout_kill_exception(mock_subprocess):
    """Test exception suppression when process.kill() fails during timeout."""
    mock_proc = MockAsyncProcess(stdout_lines=[b"running\n"], sleep_time=1.0)
    mock_proc.kill = MagicMock(side_effect=RuntimeError("Process already dead"))
    mock_subprocess.return_value = mock_proc

    result = await system.execute_shell_command("sleep 10", timeout=0.01)

    assert "Failed (Execution timed out after 0.01s)" in result
    assert "Process killed due to timeout." in result


@pytest.mark.asyncio
@patch("charon.tools.system.asyncio.create_subprocess_shell", side_effect=OSError("Permission denied"))
async def test_execute_shell_command_creation_exception(mock_subprocess):
    """Test outer exception catch when process creation fails."""
    result = await system.execute_shell_command("restricted_command")

    assert "System task execution error: Permission denied" in result
