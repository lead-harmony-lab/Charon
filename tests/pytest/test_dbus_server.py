"""Unit tests for the Charon D-Bus IPC service and GLib event loop lifecycle."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import charon.dbus_server as dbus_server_module
from charon.dbus_server import CharonDBusService, run_dbus_loop, stop_dbus_loop


@pytest.fixture
def mock_dbus_deps():
    """Patches DBus SessionBus, BusName, and Object base initialization."""
    with (
        patch("charon.dbus_server.dbus.SessionBus") as mock_bus,
        patch("charon.dbus_server.dbus.service.BusName") as mock_name,
        patch("charon.dbus_server.dbus.service.Object.__init__") as mock_obj_init,
    ):
        yield {
            "bus": mock_bus,
            "name": mock_name,
            "obj_init": mock_obj_init,
        }


@pytest.fixture
def dbus_service(mock_dbus_deps):
    """Provides a CharonDBusService instance with mocked event loop and queue."""
    mock_queue = MagicMock(spec=asyncio.Queue)
    # Use regular MagicMock for put to avoid unawaited AsyncMock coroutine warnings
    mock_queue.put = MagicMock()

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    service = CharonDBusService(async_queue=mock_queue, async_loop=mock_loop)

    # Populate dbus.service.Object internal attributes bypassed by patching __init__
    service._locations = []
    service._object_path = dbus_server_module.OBJECT_PATH
    return service


class TestCharonDBusServiceInit:
    """Tests for CharonDBusService instantiation."""

    def test_init_registers_bus_and_object(self, mock_dbus_deps):
        mock_queue = MagicMock(spec=asyncio.Queue)
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)

        service = CharonDBusService(async_queue=mock_queue, async_loop=mock_loop)

        assert service.async_queue == mock_queue
        assert service.async_loop == mock_loop
        mock_dbus_deps["bus"].assert_called_once()
        mock_dbus_deps["name"].assert_called_once_with(
            dbus_server_module.BUS_NAME, bus=mock_dbus_deps["bus"].return_value
        )
        mock_dbus_deps["obj_init"].assert_called_once_with(
            mock_dbus_deps["name"].return_value, dbus_server_module.OBJECT_PATH
        )


class TestSubmitTask:
    """Tests for the SubmitTask D-Bus endpoint."""

    @patch("charon.dbus_server.asyncio.run_coroutine_threadsafe")
    def test_submit_task_success(self, mock_run_threadsafe, dbus_service):
        task_str = "  generate cad enclosure for step motor  "
        result = dbus_service.SubmitTask(task_str)

        assert result is True
        mock_run_threadsafe.assert_called_once()
        call_args, _ = mock_run_threadsafe.call_args
        assert call_args[1] == dbus_service.async_loop

    def test_submit_task_empty_or_whitespace_returns_false(self, dbus_service):
        assert dbus_service.SubmitTask("") is False
        assert dbus_service.SubmitTask("   \n\t  ") is False

    @patch("charon.dbus_server.asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("Loop closed"))
    def test_submit_task_exception_returns_false(self, mock_run_threadsafe, dbus_service):
        result = dbus_service.SubmitTask("valid task")
        assert result is False


class TestPingAndSignals:
    """Tests for health check and D-Bus signal stub methods."""

    def test_ping_returns_pong(self, dbus_service):
        assert dbus_service.Ping() == "pong"

    def test_signal_stubs_execute_without_error(self, dbus_service):
        # Direct signal invocation safely loops over empty _locations
        dbus_service.TaskCompleted("Finished task")
        dbus_service.TaskStream("Output line chunk")
        dbus_service.GatekeeperIntercept("delete_project_workspace")
        dbus_service.ClarificationRequired("Specify target pin")


class TestSignalEmitters:
    """Tests for thread-safe GLib signal dispatch helpers."""

    @patch("charon.dbus_server.GLib.idle_add")
    def test_emit_task_completed(self, mock_idle_add, dbus_service):
        dbus_service.emit_task_completed("Task done")
        mock_idle_add.assert_called_once_with(dbus_service.TaskCompleted, "Task done")

    @patch("charon.dbus_server.GLib.idle_add")
    def test_emit_task_stream(self, mock_idle_add, dbus_service):
        dbus_service.emit_task_stream("chunk_001")
        mock_idle_add.assert_called_once_with(dbus_service.TaskStream, "chunk_001")

    @patch("charon.dbus_server.GLib.idle_add")
    def test_emit_gatekeeper_intercept(self, mock_idle_add, dbus_service):
        dbus_service.emit_gatekeeper_intercept("purge_disk")
        mock_idle_add.assert_called_once_with(dbus_service.GatekeeperIntercept, "purge_disk")

    @patch("charon.dbus_server.GLib.idle_add")
    def test_emit_clarification_required(self, mock_idle_add, dbus_service):
        dbus_service.emit_clarification_required("Need project name")
        mock_idle_add.assert_called_once_with(dbus_service.ClarificationRequired, "Need project name")


class TestDBusLoopLifecycle:
    """Tests for GLib MainLoop startup, shutdown, and exception handling."""

    def teardown_method(self):
        dbus_server_module._main_loop = None

    @patch("charon.dbus_server.GLib.MainLoop")
    def test_run_dbus_loop_success(self, mock_main_loop_cls):
        mock_loop_inst = MagicMock()
        mock_main_loop_cls.return_value = mock_loop_inst

        run_dbus_loop()

        assert dbus_server_module._main_loop == mock_loop_inst
        mock_loop_inst.run.assert_called_once()

    @patch("charon.dbus_server.GLib.MainLoop")
    def test_run_dbus_loop_handles_exception(self, mock_main_loop_cls):
        mock_loop_inst = MagicMock()
        mock_loop_inst.run.side_effect = RuntimeError("GLib loop error")
        mock_main_loop_cls.return_value = mock_loop_inst

        run_dbus_loop()
        mock_loop_inst.run.assert_called_once()

    def test_stop_dbus_loop_when_running(self):
        mock_loop_inst = MagicMock()
        mock_loop_inst.is_running.return_value = True
        dbus_server_module._main_loop = mock_loop_inst

        stop_dbus_loop()

        mock_loop_inst.quit.assert_called_once()

    def test_stop_dbus_loop_when_not_running(self):
        mock_loop_inst = MagicMock()
        mock_loop_inst.is_running.return_value = False
        dbus_server_module._main_loop = mock_loop_inst

        stop_dbus_loop()

        mock_loop_inst.quit.assert_not_called()

    def test_stop_dbus_loop_when_none(self):
        dbus_server_module._main_loop = None
        stop_dbus_loop()
