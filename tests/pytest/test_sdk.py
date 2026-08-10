#!/usr/bin/env python3
"""Tests for Charon Python Client SDK (charon/sdk.py)."""

import asyncio
import importlib
import json
import os
import shutil
import socket
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

import charon.sdk as sdk_module
from charon.gateway.models import GatekeeperDecision, TaskRequest, TaskResponse, WSEvent
from charon.sdk import CharonClientNode, HardwareTelemetry, _dump_model


# ==============================================================================
# Helper & Serialization Tests
# ==============================================================================

class TestDumpModel:
    """Tests for the `_dump_model` helper function across Pydantic versions."""

    def test_dump_pydantic_v2_model(self):
        """Tests serialization of a Pydantic v2 model with model_dump."""
        event = WSEvent(event_type="status_change", client_id="client_1", data={"key": "val"})
        result = _dump_model(event)
        assert isinstance(result, dict)
        assert result["event_type"] == "status_change"
        assert result["client_id"] == "client_1"
        assert result["data"] == {"key": "val"}

    def test_dump_pydantic_v1_legacy_fallback(self):
        """Tests fallback serialization when model_dump is missing but dict exists."""
        mock_v1_model = MagicMock()
        del mock_v1_model.model_dump  # Remove v2 method to trigger v1 branch
        mock_v1_model.dict.return_value = {"event_type": "legacy_v1"}

        result = _dump_model(mock_v1_model)
        assert result == {"event_type": "legacy_v1"}
        mock_v1_model.dict.assert_called_once()

    def test_dump_plain_dict(self):
        """Tests serialization when payload is already a standard dictionary."""
        payload = {"foo": "bar", "num": 42}
        assert _dump_model(payload) == payload

    def test_dump_generic_object(self):
        """Tests dictionary conversion fallback for generic objects or iterables."""
        items = [("a", 1), ("b", 2)]
        assert _dump_model(items) == {"a": 1, "b": 2}


# ==============================================================================
# Hardware Telemetry Tests
# ==============================================================================

class TestHardwareTelemetry:
    """Tests for system architecture and hardware telemetry discovery."""

    def test_get_local_ip_success(self):
        """Tests local IP resolution on active outbound socket connection."""
        mock_socket_inst = MagicMock()
        mock_socket_inst.getsockname.return_value = ("192.168.1.100", 54321)

        with patch("socket.socket") as mock_socket_cls:
            mock_socket_cls.return_value.__enter__.return_value = mock_socket_inst
            ip = HardwareTelemetry.get_local_ip()
            assert ip == "192.168.1.100"

    def test_get_local_ip_failure_fallback(self):
        """Tests fallback to localhost IP when socket creation or connection fails."""
        with patch("socket.socket", side_effect=OSError("Network unreachable")):
            ip = HardwareTelemetry.get_local_ip()
            assert ip == "127.0.0.1"

    def test_detect_gpus_with_nvidia_smi(self):
        """Tests GPU detection when nvidia-smi tool is available on system path."""
        mock_res = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090\nNVIDIA GeForce RTX 3090\n",
        )
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
                "subprocess.run", return_value=mock_res
        ):
            gpus = HardwareTelemetry.detect_gpus()
            assert gpus == ["NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 3090"]

    def test_detect_gpus_without_nvidia_smi(self):
        """Tests GPU fallback when nvidia-smi utility is absent."""
        with patch("shutil.which", return_value=None):
            gpus = HardwareTelemetry.detect_gpus()
            assert gpus == ["None (CPU Only)"]

    def test_detect_gpus_subprocess_error(self):
        """Tests GPU fallback on nvidia-smi command failure or timeout."""
        with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch(
                "subprocess.run", side_effect=Exception("Subprocess error")
        ):
            gpus = HardwareTelemetry.detect_gpus()
            assert gpus == ["None (CPU Only)"]

    def test_detect_usb_devices_with_lsusb(self):
        """Tests USB device parsing when lsusb is available."""
        lsusb_out = (
            "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"
            "Bus 002 Device 003: ID 046d:c52b Logitech, Inc. Unifying Receiver\n"
        )
        mock_res = MagicMock(returncode=0, stdout=lsusb_out)
        with patch("shutil.which", return_value="/usr/bin/lsusb"), patch(
                "subprocess.run", return_value=mock_res
        ):
            devices = HardwareTelemetry.detect_usb_devices()
            assert len(devices) == 2
            assert "Linux Foundation 2.0 root hub" in devices[0]
            assert "Logitech, Inc. Unifying Receiver" in devices[1]

    def test_detect_usb_devices_cap_at_10(self):
        """Tests USB device list capping at 10 items to prevent payload bloat."""
        lines = [f"Bus 001 Device 00{i}: ID 0000:0000 Device {i}" for i in range(15)]
        mock_res = MagicMock(returncode=0, stdout="\n".join(lines))
        with patch("shutil.which", return_value="/usr/bin/lsusb"), patch(
                "subprocess.run", return_value=mock_res
        ):
            devices = HardwareTelemetry.detect_usb_devices()
            assert len(devices) == 10

    def test_detect_usb_devices_no_lsusb(self):
        """Tests USB discovery when lsusb tool is absent."""
        with patch("shutil.which", return_value=None):
            devices = HardwareTelemetry.detect_usb_devices()
            assert devices == []

    def test_collect_full_telemetry(self):
        """Tests complete system telemetry snapshot aggregation."""
        with patch("shutil.disk_usage", return_value=(100 * 1024 ** 3, 50 * 1024 ** 3, 50 * 1024 ** 3)), \
                patch.object(HardwareTelemetry, "get_local_ip", return_value="10.0.0.5"), \
                patch.object(HardwareTelemetry, "detect_gpus", return_value=["Mock GPU"]), \
                patch.object(HardwareTelemetry, "detect_usb_devices", return_value=["Mock USB"]):
            telemetry = HardwareTelemetry.collect()

            assert telemetry["ip_address"] == "10.0.0.5"
            assert telemetry["disk"]["total_gb"] == 100.0
            assert telemetry["disk"]["free_gb"] == 50.0
            assert telemetry["gpus"] == ["Mock GPU"]
            assert telemetry["usb_devices"] == ["Mock USB"]
            assert "hostname" in telemetry
            assert "cpu_cores" in telemetry

    def test_collect_disk_usage_exception_fallback(self):
        """Tests telemetry collection fallback when disk usage inspection fails."""
        with patch("shutil.disk_usage", side_effect=PermissionError("Access denied")):
            telemetry = HardwareTelemetry.collect()
            assert telemetry["disk"] == {"total_gb": 0, "free_gb": 0}


# ==============================================================================
# CharonClientNode Initialization & Config Tests
# ==============================================================================

class TestCharonClientNodeInit:
    """Tests SDK client initialization and configuration."""

    def test_init_default_and_ws_url_derivation(self):
        """Tests default parameters and WebSocket URL derivation for HTTP engine URL."""
        node = CharonClientNode(client_id="node_1", engine_url="http://localhost:8000", api_key="secret123")
        assert node.client_id == "node_1"
        assert node.engine_url == "http://localhost:8000"
        assert node.api_key == "secret123"
        assert node.ws_url.startswith("ws://localhost:8000/v1/ws?")
        assert "client_id=node_1" in node.ws_url
        assert "api_key=secret123" in node.ws_url
        assert not node.is_connected

    def test_init_wss_scheme_for_https(self):
        """Tests secure WSS scheme generation for HTTPS engine URLs."""
        node = CharonClientNode(
            client_id="node_secure",
            engine_url="https://charon.example.com:8443/",
            auto_discover_hardware=False,
        )
        assert node.engine_url == "https://charon.example.com:8443"
        assert node.ws_url.startswith("wss://charon.example.com:8443/v1/ws?")

    def test_init_without_hardware_discovery(self):
        """Tests initializing without auto hardware discovery."""
        node = CharonClientNode(client_id="node_no_hw", auto_discover_hardware=False)
        assert node.telemetry == {}
        assert "telemetry" not in node.default_context

    def test_refresh_telemetry(self):
        """Tests manual telemetry refresh updates node state and default context."""
        node = CharonClientNode(client_id="node_refresh", auto_discover_hardware=False)
        assert "telemetry" not in node.default_context

        with patch.object(HardwareTelemetry, "collect", return_value={"mock": "data"}):
            telemetry = node.refresh_telemetry()
            assert telemetry == {"mock": "data"}
            assert node.default_context["telemetry"] == {"mock": "data"}


# ==============================================================================
# Event Router & Registration Tests
# ==============================================================================

class TestCharonClientNodeEvents:
    """Tests handler registration and WebSocket event routing."""

    def test_register_handler_and_decorator(self):
        """Tests registering event handlers manually and via @node.on decorator."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)

        async def handler1(event: WSEvent):
            pass

        async def handler2(event: WSEvent):
            pass

        node.register_handler("task_submitted", handler1)
        node.on("task_completed")(handler2)

        assert handler1 in node._handlers["task_submitted"]
        assert handler2 in node._handlers["task_completed"]

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_targeted_and_wildcard_handlers(self):
        """Tests dispatching incoming WebSocket payloads to targeted and wildcard handlers."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)

        called_events = []

        async def specific_handler(event: WSEvent):
            called_events.append(f"specific:{event.event_type}")

        async def wildcard_handler(event: WSEvent):
            called_events.append(f"wildcard:{event.event_type}")

        node.register_handler("status_change", specific_handler)
        node.register_handler("*", wildcard_handler)

        raw_payload = json.dumps({
            "event_type": "status_change",
            "task_id": "task_123",
            "client_id": "test_node",
            "data": {"status": "ok"},
        })

        await node._dispatch_ws_message(raw_payload)

        assert "specific:status_change" in called_events
        assert "wildcard:status_change" in called_events

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_unhandled_event(self):
        """Tests that events without registered handlers do not raise errors."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)
        raw_payload = json.dumps({"event_type": "system_alert", "data": {}})

        # Should complete gracefully without raising
        await node._dispatch_ws_message(raw_payload)

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_invalid_json(self):
        """Tests error resilience when receiving malformed JSON payload."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)
        await node._dispatch_ws_message("NOT VALID JSON {{{")

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_logs_unhandled_event(self):
        """Tests that dispatching an event with no handlers logs a debug message and returns."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)
        raw_payload = json.dumps({"event_type": "system_alert", "data": {}})

        with patch("charon.sdk.logger.debug") as mock_debug:
            await node._dispatch_ws_message(raw_payload)
            mock_debug.assert_called_with("No handlers registered for event type 'system_alert'")


# ==============================================================================
# Connection Lifecycle & Reconnection Loop Tests
# ==============================================================================

class TestCharonClientNodeConnection:
    """Tests connection, disconnection, background listening, and reconnect loop."""

    @pytest.mark.asyncio
    async def test_connect_already_running_aborts(self):
        """Tests that connect() exits early if the node is already running."""
        node = CharonClientNode(client_id="running_node", auto_discover_hardware=False)
        node._running = True

        with patch("charon.sdk.logger.warning") as mock_warn:
            await node.connect()
            mock_warn.assert_called_with("Node 'running_node' is already running.")
            # Ensure it didn't create a new task or client
            assert node._http_client is None

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        """Tests initiating connection and tearing down HTTP and background listener tasks."""
        node = CharonClientNode(client_id="conn_node", auto_discover_hardware=False)

        with patch.object(node, "_ws_loop", side_effect=asyncio.CancelledError):
            await node.connect()
            assert node._running is True
            assert node._http_client is not None
            assert node._listener_task is not None

            # Secondary connect call should log warning and return early
            await node.connect()

            await node.disconnect()
            assert node._running is False
            assert node._connected is False
            assert node._http_client is None

    @pytest.mark.asyncio
    async def test_disconnect_full_cleanup(self):
        """Tests complete cleanup of active websocket connection and background listener task."""
        node = CharonClientNode(client_id="cleanup_node", auto_discover_hardware=False)
        node._running = True
        node._connected = True

        mock_ws = AsyncMock()
        node._ws_connection = mock_ws
        node._http_client = AsyncMock()

        async def mock_loop():
            await asyncio.sleep(10)

        node._listener_task = asyncio.create_task(mock_loop())

        await node.disconnect()

        mock_ws.close.assert_called_once()
        assert not node.is_connected
        assert node._ws_connection is None
        assert node._http_client is None

    @pytest.mark.asyncio
    async def test_disconnect_catches_cancelled_error(self):
        """Tests that disconnect() gracefully handles CancelledError from the listener task."""
        node = CharonClientNode(client_id="cancel_node", auto_discover_hardware=False)
        node._running = True

        async def cancelled_task():
            raise asyncio.CancelledError()

        node._listener_task = asyncio.create_task(cancelled_task())

        # Should complete without raising an exception
        await node.disconnect()
        assert node._running is False

    @pytest.mark.asyncio
    async def test_listen_forever(self):
        """Tests listen_forever auto-connects and awaits listener task."""
        node = CharonClientNode(client_id="listen_node", auto_discover_hardware=False)

        mock_task = asyncio.create_task(asyncio.sleep(0.01))

        with patch.object(node, "connect", AsyncMock()) as mock_connect:
            node._listener_task = mock_task
            await node.listen_forever()
            mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_listen_forever_catches_cancelled_error(self):
        """Tests that listen_forever() gracefully handles CancelledError."""
        node = CharonClientNode(client_id="cancel_node", auto_discover_hardware=False)

        async def cancelled_task():
            raise asyncio.CancelledError()

        node._listener_task = asyncio.create_task(cancelled_task())

        # Should complete without raising an exception
        await node.listen_forever()

    @pytest.mark.asyncio
    async def test_ws_loop_reconnect_disabled_exits_on_drop(self):
        """Tests that WebSocket loop terminates immediately if auto_reconnect is False."""
        node = CharonClientNode(
            client_id="no_reconn_node",
            auto_reconnect=False,
            auto_discover_hardware=False,
        )
        node._running = True

        with patch("websockets.connect", side_effect=ConnectionClosedOK(rcvd=None, sent=None)):
            await node._ws_loop()
            assert node._connected is False

    @pytest.mark.asyncio
    async def test_ws_loop_reconnect_backoff_and_exit(self):
        """Tests exponential backoff delay during WebSocket reconnection attempts."""
        node = CharonClientNode(
            client_id="backoff_node",
            auto_reconnect=True,
            auto_discover_hardware=False,
        )
        node._running = True

        async def fake_sleep(delay):
            # Stop the loop after entering backoff so pytest doesn't hang infinitely
            node._running = False

        with patch("websockets.connect", side_effect=ConnectionError("Connection lost")), \
                patch("asyncio.sleep", side_effect=fake_sleep) as mock_sleep:
            await node._ws_loop()
            mock_sleep.assert_called_once_with(1.0)

    @pytest.mark.asyncio
    async def test_ws_loop_exits_cleanly_when_stopped_during_error(self):
        """Tests that _ws_loop breaks without reconnecting if node is stopped during an error."""
        node = CharonClientNode(
            client_id="stop_node",
            auto_discover_hardware=False,
            auto_reconnect=True  # Ensure auto_reconnect is True to test the bypass
        )
        node._running = True

        def trigger_error_and_stop(*args, **kwargs):
            # Simulate another thread/task calling disconnect() right as the error occurs
            node._running = False
            raise OSError("Network unreachable")

        with patch("websockets.connect", side_effect=trigger_error_and_stop), \
                patch("asyncio.sleep") as mock_sleep:
            await node._ws_loop()

            # The loop should break immediately; no backoff sleep should be called
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_loop_receives_message_and_dispatches(self):
        """Tests WebSocket loop establishing connection, reading a message, and clean shutdown."""
        node = CharonClientNode(
            client_id="recv_node",
            auto_reconnect=False,
            auto_discover_hardware=False,
        )
        node._running = True

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"event_type": "status_change", "data": {}}),
            ConnectionClosedOK(rcvd=None, sent=None),
        ])

        mock_connect_cm = AsyncMock()
        mock_connect_cm.__aenter__.return_value = mock_ws
        mock_connect_cm.__aexit__.return_value = None

        with patch("websockets.connect", return_value=mock_connect_cm), \
                patch.object(node, "_dispatch_ws_message", AsyncMock()) as mock_dispatch:
            await node._ws_loop()

            mock_dispatch.assert_called_once()
            call_arg = mock_dispatch.call_args[0][0]
            assert "status_change" in call_arg


# ==============================================================================
# REST API Client Methods Tests
# ==============================================================================

class TestCharonClientNodeREST:
    """Tests SDK REST API interaction methods."""

    @pytest.mark.asyncio
    async def test_rest_methods_unconnected_raise_runtime_error(self):
        """Tests that REST calls fail if node is not connected."""
        node = CharonClientNode(client_id="unconn_node", auto_discover_hardware=False)

        with pytest.raises(RuntimeError, match="SDK client not connected"):
            await node.check_health()

        with pytest.raises(RuntimeError, match="SDK client not connected"):
            await node.get_connected_clients()

        with pytest.raises(RuntimeError, match="SDK client not connected"):
            await node.submit_task("test prompt")

        with pytest.raises(RuntimeError, match="SDK client not connected"):
            await node.respond_gatekeeper("app_1", "proceed")

    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """Tests querying daemon health endpoint."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_res = MagicMock()
        mock_res.json.return_value = {"status": "ok", "version": "1.0.0"}
        mock_res.raise_for_status.return_value = None
        mock_http.get.return_value = mock_res

        node._http_client = mock_http

        health = await node.check_health()
        assert health == {"status": "ok", "version": "1.0.0"}
        mock_http.get.assert_called_once_with("/v1/health")

    @pytest.mark.asyncio
    async def test_get_connected_clients_success(self):
        """Tests querying connected peripheral clients endpoint."""
        node = CharonClientNode(client_id="test_node", auto_discover_hardware=False)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_res = MagicMock()
        mock_res.json.return_value = {"clients": ["node1", "node2"]}
        mock_res.raise_for_status.return_value = None
        mock_http.get.return_value = mock_res

        node._http_client = mock_http

        clients = await node.get_connected_clients()
        assert clients == {"clients": ["node1", "node2"]}
        mock_http.get.assert_called_once_with("/v1/clients")

    @pytest.mark.asyncio
    async def test_submit_task_success(self):
        """Tests submitting a task request to Charon daemon."""
        node = CharonClientNode(
            client_id="task_client",
            auto_discover_hardware=False,
            default_context={"env": "prod"},
        )
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_res = MagicMock()
        mock_res.json.return_value = {
            "task_id": "task_999",
            "status": "queued",
            "assigned_agent": "orchestrator",
            "message": "Task received",
        }
        mock_res.raise_for_status.return_value = None
        mock_http.post.return_value = mock_res

        node._http_client = mock_http

        response = await node.submit_task(
            prompt="Analyze system logs",
            agent_override="log_agent",
            context={"level": "error"},
        )

        assert isinstance(response, TaskResponse)
        assert response.task_id == "task_999"
        assert response.status == "queued"
        assert response.assigned_agent == "orchestrator"

        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/v1/task"
        sent_json = call_args[1]["json"]
        assert sent_json["prompt"] == "Analyze system logs"
        assert sent_json["client_id"] == "task_client"
        assert sent_json["agent_override"] == "log_agent"
        assert sent_json["context"] == {"env": "prod", "level": "error"}

    @pytest.mark.asyncio
    async def test_respond_gatekeeper_success(self):
        """Tests responding to a Gatekeeper authorization interception."""
        node = CharonClientNode(client_id="gatekeeper_client", auto_discover_hardware=False)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_res = MagicMock()
        mock_res.json.return_value = {"status": "decision_recorded", "approval_id": "app_555"}
        mock_res.raise_for_status.return_value = None
        mock_http.post.return_value = mock_res

        node._http_client = mock_http

        result = await node.respond_gatekeeper(
            approval_id="app_555",
            decision="proceed",
            notes="Authorized by operator",
        )

        assert result["status"] == "decision_recorded"
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/v1/gatekeeper/respond"
        sent_json = call_args[1]["json"]
        assert sent_json["approval_id"] == "app_555"
        assert sent_json["decision"] == "proceed"
        assert sent_json["client_id"] == "gatekeeper_client"
        assert sent_json["notes"] == "Authorized by operator"


# ==============================================================================
# Standalone SDK Import Fallback Tests
# ==============================================================================

class TestStandaloneSDKFallbacks:
    """Tests SDK behavior when running on isolated peripheral nodes lacking core daemon modules."""

    def test_standalone_import_fallbacks(self, tmp_path):
        """Tests standalone edge node fallback when charon config and models are missing."""
        env_file = tmp_path / "env"
        env_file.write_text("CHARON_API_KEY=fallback-secret-key\n# Comment Line\n")

        with patch.dict(sys.modules, {"charon.config": None, "charon.gateway.models": None}), \
                patch("os.path.expanduser", return_value=str(env_file)), \
                patch.dict(os.environ, {}, clear=True):

            reloaded_sdk = importlib.reload(sdk_module)
            try:
                assert reloaded_sdk.CHARON_API_KEY == "fallback-secret-key"
                ws_event = reloaded_sdk.WSEvent(event_type="custom_event")
                assert ws_event.event_type == "custom_event"
            finally:
                # Restore module state
                importlib.reload(sdk_module)

    def test_standalone_import_env_read_exception(self, tmp_path):
        """Tests fallback handling when ~/.config/charon/env exists but cannot be read."""
        env_dir = tmp_path / "env"
        env_dir.mkdir()  # Create a directory instead of a file to force an IOError

        with patch.dict(sys.modules, {"charon.config": None, "charon.gateway.models": None}), \
                patch("os.path.expanduser", return_value=str(env_dir)), \
                patch.dict(os.environ, {}, clear=True):

            reloaded_sdk = importlib.reload(sdk_module)
            try:
                # Should silently pass the exception and fall back to the default
                assert reloaded_sdk.CHARON_API_KEY == "charon-secret-key-change-me"
            finally:
                importlib.reload(sdk_module)


class TestSDKMissingBranchCoverage:
    """Targeted tests to cover remaining branch edge cases in charon/sdk.py."""

    def test_standalone_import_no_env_file_no_env_var(self, tmp_path):
        """Covers branch 31->42: Standalone fallback when CHARON_API_KEY is absent and env file does not exist."""
        non_existent_file = tmp_path / "non_existent_env"

        with patch.dict(sys.modules, {"charon.config": None, "charon.gateway.models": None}), \
                patch("os.path.expanduser", return_value=str(non_existent_file)), \
                patch.dict(os.environ, {}, clear=True):

            reloaded_sdk = importlib.reload(sdk_module)
            try:
                assert reloaded_sdk.CHARON_API_KEY == "charon-secret-key-change-me"
            finally:
                importlib.reload(sdk_module)

    def test_detect_usb_devices_nonzero_returncode(self):
        """Covers branch 129->137: lsusb returns a non-zero exit status."""
        mock_res = MagicMock(returncode=1, stdout="")
        with patch("shutil.which", return_value="/usr/bin/lsusb"), \
                patch("subprocess.run", return_value=mock_res):
            assert HardwareTelemetry.detect_usb_devices() == []

    def test_detect_usb_devices_malformed_lines(self):
        """Covers branch where lsusb output lines contain fewer than 3 colon-separated parts."""
        malformed_stdout = (
            "Bus 001 Device 001\n"  # No colons (fewer than 3 parts)
            "Bus 001 Device 002: ID 1234\n"  # Only 1 colon (fewer than 3 parts)
            "Bus 002 Device 003: ID 046d:c52b Logitech, Inc. Receiver\n"  # Valid (2 colons -> 3 parts)
        )
        mock_res = MagicMock(returncode=0, stdout=malformed_stdout)
        with patch("shutil.which", return_value="/usr/bin/lsusb"), \
             patch("subprocess.run", return_value=mock_res):
            devices = HardwareTelemetry.detect_usb_devices()
            assert len(devices) == 1
            assert devices[0] == "c52b Logitech, Inc. Receiver"

    def test_collect_cpu_count_none_fallback(self):
        """Covers fallback branch when os.cpu_count() returns None."""
        with patch("os.cpu_count", return_value=None):
            telemetry = HardwareTelemetry.collect()
            assert telemetry["cpu_cores"] == 1

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_exception_handling(self):
        """Covers line 322: Error logging when payload parsing or handling raises an unexpected exception."""
        node = CharonClientNode(client_id="err_node", auto_discover_hardware=False)

        # Force an unexpected exception during WSEvent instantiating/dispatching
        with patch("charon.sdk.WSEvent", side_effect=ValueError("Unexpected parsing crash")):
            with patch("charon.sdk.logger.error") as mock_logger_error:
                raw_payload = json.dumps({"event_type": "status_change", "data": {}})
                await node._dispatch_ws_message(raw_payload)

                mock_logger_error.assert_called_once()
                assert "Error parsing or handling WebSocket event payload" in mock_logger_error.call_args[0][0]


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

    @pytest.mark.asyncio
    async def test_dispatch_ws_message_exception_line(self):
        """Covers line 322: Exception logging during WS dispatch handling."""
        node = CharonClientNode(client_id="error_node", auto_discover_hardware=False)

        # Pass completely invalid JSON to trigger the try...except block on line 322
        invalid_payload = "{ malformed json..."

        with patch("charon.sdk.logger.error") as mock_log:
            await node._dispatch_ws_message(invalid_payload)
            mock_log.assert_called_once()
            assert "Error parsing or handling WebSocket event payload" in mock_log.call_args[0][0]
