import asyncio
import json
import logging
import os
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

from charon.gateway.bridge import WebSocketDBusBridge, main


class TestWebSocketDBusBridge:
    @pytest.fixture
    def mock_gio(self):
        with patch("charon.gateway.bridge.Gio") as mock_gio, patch(
            "charon.gateway.bridge.GLib"
        ) as mock_glib:
            mock_bus = MagicMock()
            mock_gio.bus_get_sync.return_value = mock_bus
            mock_gio.BusType.SESSION = "SESSION"
            yield {"gio": mock_gio, "glib": mock_glib, "bus": mock_bus}

    def test_init_dbus_success(self, mock_gio):
        bridge = WebSocketDBusBridge()
        assert bridge.bus is not None
        mock_gio["gio"].bus_get_sync.assert_called_once_with("SESSION", None)

    def test_init_dbus_failure(self, mock_gio, caplog):
        mock_gio["gio"].bus_get_sync.side_effect = Exception("D-Bus Bus Error")
        with caplog.at_level(logging.ERROR):
            bridge = WebSocketDBusBridge()
            assert bridge.bus is None
            assert "Failed to connect to Session D-Bus: D-Bus Bus Error" in caplog.text

    def test_emit_dbus_signal_success(self, mock_gio):
        bridge = WebSocketDBusBridge()
        bridge.emit_dbus_signal("TestSignal", "payload_data")

        mock_gio["bus"].emit_signal.assert_called_once_with(
            None,
            "/org/charon/Daemon",
            "org.charon.Interface",
            "TestSignal",
            mock_gio["glib"].Variant.return_value,
        )
        mock_gio["glib"].Variant.assert_called_once_with("(s)", ("payload_data",))

    def test_emit_dbus_signal_reconnect_retry(self, mock_gio, caplog):
        bridge = WebSocketDBusBridge()
        bridge.bus = None  # Force initial disconnect

        with caplog.at_level(logging.WARNING):
            bridge.emit_dbus_signal("TestSignal", "payload_data")
            assert (
                "D-Bus connection unavailable. Re-attempting connection..."
                in caplog.text
            )
            assert bridge.bus is not None
            mock_gio["bus"].emit_signal.assert_called_once()

    def test_emit_dbus_signal_reconnect_failure(self, mock_gio, caplog):
        bridge = WebSocketDBusBridge()
        bridge.bus = None
        mock_gio["gio"].bus_get_sync.side_effect = Exception("Permanent DBus Error")

        with caplog.at_level(logging.WARNING):
            bridge.emit_dbus_signal("TestSignal", "payload_data")
            assert (
                "D-Bus connection unavailable. Re-attempting connection..."
                in caplog.text
            )
            assert bridge.bus is None

    def test_emit_dbus_signal_exception_during_emit(self, mock_gio, caplog):
        bridge = WebSocketDBusBridge()
        mock_gio["bus"].emit_signal.side_effect = Exception("Emission Error")

        with caplog.at_level(logging.ERROR):
            bridge.emit_dbus_signal("TestSignal", "payload_data")
            assert "Failed to emit D-Bus signal 'TestSignal': Emission Error" in caplog.text

    @pytest.mark.asyncio
    async def test_connect_and_listen_events_handling(self, mock_gio):
        bridge = WebSocketDBusBridge()

        # Simulated event messages sent over the WebSocket stream
        messages = [
            json.dumps({"event_type": "status_change", "data": {"prompt": "Building CAD"}}),
            json.dumps({"event_type": "status_change", "data": {"message": "Slicing model"}}),
            json.dumps({"event_type": "status_change", "data": {}}),  # Fallback to "Executing"
            json.dumps({"event_type": "gatekeeper_intercept", "data": {"action": "Approve"}}),
            json.dumps({"event_type": "gatekeeper_intercept", "data": {}}),  # Fallback
            json.dumps({"event_type": "task_complete", "data": {"summary": "Done!"}}),
            json.dumps({"event_type": "task_complete", "data": {}}),  # Fallback
            "INVALID_JSON_STRING",  # Malformed JSON coverage
            json.dumps({"event_type": "ignored_event", "data": {}}),
        ]

        async def mock_async_iter():
            for msg in messages:
                yield msg

        mock_ws = MagicMock()
        mock_ws.__aiter__.side_effect = lambda: mock_async_iter()

        mock_connect = MagicMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=None)

        # Patch websockets.connect to yield our mock WS connection and then raise CancelledError to exit loop
        with patch("websockets.connect", side_effect=[mock_connect, asyncio.CancelledError()]):
            with patch.object(bridge, "emit_dbus_signal") as mock_emit:
                await bridge.connect_and_listen()

                # Verify mapped signals were emitted correctly
                expected_emits = [
                    ("StatusChanged", "Building CAD"),
                    ("StatusChanged", "Slicing model"),
                    ("StatusChanged", "Executing"),
                    ("GatekeeperIntercept", "Approve"),
                    ("GatekeeperIntercept", "Unspecified Gatekeeper Request"),
                    ("TaskCompleted", "Done!"),
                    ("TaskCompleted", "Task complete."),
                ]
                assert mock_emit.call_count == len(expected_emits)
                for expected in expected_emits:
                    mock_emit.assert_any_call(*expected)

    @pytest.mark.asyncio
    @patch("charon.gateway.bridge.CHARON_API_KEY", "")  # Forces 'headers' to be {} covering branch 82->85
    async def test_connect_and_listen_connection_closed_and_retry(self, mock_gio, caplog):
        bridge = WebSocketDBusBridge()

        # Simulate ConnectionClosedError first, then CancelledError to gracefully exit
        err = websockets.exceptions.ConnectionClosedError(rcvd=None, sent=None)

        with patch("websockets.connect", side_effect=[err, asyncio.CancelledError()]):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with caplog.at_level(logging.WARNING):
                    await bridge.connect_and_listen()
                    assert "Gateway offline or connection lost" in caplog.text
                    mock_sleep.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_connect_and_listen_unexpected_exception(self, mock_gio, caplog):
        bridge = WebSocketDBusBridge()

        # Simulate generic Exception first, then CancelledError to exit
        err = Exception("Unexpected connection crash")

        with patch("websockets.connect", side_effect=[err, asyncio.CancelledError()]):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with caplog.at_level(logging.ERROR):
                    await bridge.connect_and_listen()
                    assert "Unexpected bridge error: Unexpected connection crash" in caplog.text
                    mock_sleep.assert_called_once_with(5)


class TestBridgeMainCLI:
    def test_main_graceful_shutdown(self):
        with patch("charon.gateway.bridge.WebSocketDBusBridge") as mock_bridge_cls:
            mock_bridge_instance = MagicMock()
            mock_bridge_cls.return_value = mock_bridge_instance

            with patch("asyncio.run", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def test_main_execution(self):
        with patch("charon.gateway.bridge.WebSocketDBusBridge") as mock_bridge_cls:
            mock_bridge_instance = MagicMock()
            mock_bridge_cls.return_value = mock_bridge_instance

            with patch("asyncio.run") as mock_asyncio_run:
                main()
                mock_asyncio_run.assert_called_once_with(
                    mock_bridge_instance.connect_and_listen()
                )

    def test_config_import_fallback(self, monkeypatch):
        """Verify fallback constants when charon.config is unavailable."""
        import importlib

        import charon.gateway.bridge as bridge_module

        # 1. Hide charon.config using pytest's built-in fixture
        monkeypatch.setitem(sys.modules, "charon.config", None)

        try:
            # 2. Force re-evaluation of top-level import block
            importlib.reload(bridge_module)

            assert bridge_module.API_KEY_HEADER_NAME == "X-API-Key"
            assert bridge_module.CHARON_API_KEY == os.getenv("CHARON_API_KEY", "")
        finally:
            # 3. Always restore default module state, even if assertions fail
            monkeypatch.undo()
            importlib.reload(bridge_module)

    def test_module_entrypoint(self):
        """Verify execution of the if __name__ == '__main__' branch."""
        with patch("asyncio.run") as mock_asyncio_run, \
             patch("charon.gateway.bridge.Gio"):
            runpy.run_module("charon.gateway.bridge", run_name="__main__")
            mock_asyncio_run.assert_called_once()
