from unittest.mock import AsyncMock, MagicMock
import pytest

from charon.gateway.models import WSEvent
from charon.gateway.ws import ConnectionManager


@pytest.fixture
def manager() -> ConnectionManager:
    """Fixture providing a fresh ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def mock_event() -> MagicMock:
    """Fixture providing a mocked WSEvent."""
    event = MagicMock(spec=WSEvent)
    event.model_dump.return_value = {"type": "test_event", "payload": {}}
    return event


# ============================================================================
# Connect Tests
# ============================================================================

@pytest.mark.asyncio
async def test_connect_with_client_id(manager: ConnectionManager):
    ws = AsyncMock()
    await manager.connect(ws, client_id="client_1")

    ws.accept.assert_called_once()
    assert ws in manager.active_connections
    assert ws in manager.client_sockets["client_1"]


@pytest.mark.asyncio
async def test_connect_without_client_id(manager: ConnectionManager):
    ws = AsyncMock()
    await manager.connect(ws, client_id=None)

    ws.accept.assert_called_once()
    assert ws in manager.active_connections
    assert manager.client_sockets == {}


@pytest.mark.asyncio
async def test_connect_duplicate_socket(manager: ConnectionManager):
    """Hits branches where socket is already in active_connections and client_sockets."""
    ws = AsyncMock()
    await manager.connect(ws, client_id="client_1")
    # Duplicate connect attempt with same socket instance
    await manager.connect(ws, client_id="client_1")

    assert manager.active_connections.count(ws) == 1
    assert manager.client_sockets["client_1"].count(ws) == 1


# ============================================================================
# Disconnect Tests
# ============================================================================

def test_disconnect_clean_up(manager: ConnectionManager):
    """Tests removing sockets and pruning empty client_id keys."""
    ws1 = MagicMock()
    ws2 = MagicMock()

    manager.active_connections = [ws1, ws2]
    manager.client_sockets = {"client_1": [ws1, ws2], "client_2": [ws2]}

    # Disconnect ws1: client_1 still has ws2, so client_1 key persists
    manager.disconnect(ws1)
    assert ws1 not in manager.active_connections
    assert ws1 not in manager.client_sockets["client_1"]
    assert "client_1" in manager.client_sockets

    # Disconnect ws2: both client entries become empty and get deleted
    manager.disconnect(ws2)
    assert ws2 not in manager.active_connections
    assert "client_1" not in manager.client_sockets
    assert "client_2" not in manager.client_sockets


def test_disconnect_unregistered_socket(manager: ConnectionManager):
    """Hits branch where websocket is not in active_connections."""
    ws = MagicMock()
    manager.disconnect(ws)  # Should execute smoothly without raising key errors


# ============================================================================
# Broadcast Tests
# ============================================================================

@pytest.mark.asyncio
async def test_broadcast_success(manager: ConnectionManager, mock_event: MagicMock):
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    manager.active_connections = [ws1, ws2]

    await manager.broadcast(mock_event)

    expected_payload = {"type": "test_event", "payload": {}}
    ws1.send_json.assert_called_once_with(expected_payload)
    ws2.send_json.assert_called_once_with(expected_payload)
    assert len(manager.active_connections) == 2


@pytest.mark.asyncio
async def test_broadcast_socket_failure(manager: ConnectionManager, mock_event: MagicMock):
    """Hits try/except error path during broadcast and verifies auto-disconnection."""
    ws_good = AsyncMock()
    ws_bad = AsyncMock()
    ws_bad.send_json.side_effect = RuntimeError("Broken pipe")

    manager.active_connections = [ws_good, ws_bad]

    await manager.broadcast(mock_event)

    ws_good.send_json.assert_called_once()
    ws_bad.send_json.assert_called_once()
    assert ws_good in manager.active_connections
    assert ws_bad not in manager.active_connections


# ============================================================================
# Send To Client Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_to_client_success(manager: ConnectionManager, mock_event: MagicMock):
    ws = AsyncMock()
    manager.client_sockets = {"client_1": [ws]}

    await manager.send_to_client("client_1", mock_event)

    ws.send_json.assert_called_once_with({"type": "test_event", "payload": {}})


@pytest.mark.asyncio
async def test_send_to_client_fallback_broadcast(manager: ConnectionManager, mock_event: MagicMock):
    """Hits branch where client_id has no sockets and falls back to broadcast."""
    ws = AsyncMock()
    manager.active_connections = [ws]

    await manager.send_to_client("unknown_client", mock_event)

    ws.send_json.assert_called_once_with({"type": "test_event", "payload": {}})


@pytest.mark.asyncio
async def test_send_to_client_socket_failure(manager: ConnectionManager, mock_event: MagicMock):
    """Hits try/except path in send_to_client and disconnects broken sockets."""
    ws_good = AsyncMock()
    ws_bad = AsyncMock()
    ws_bad.send_json.side_effect = ConnectionResetError("Connection lost")

    manager.active_connections = [ws_good, ws_bad]
    manager.client_sockets = {"client_1": [ws_good, ws_bad]}

    await manager.send_to_client("client_1", mock_event)

    assert ws_good in manager.client_sockets["client_1"]
    assert ws_bad not in manager.active_connections
    assert ws_bad not in manager.client_sockets["client_1"]
