from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.routes import router


@pytest.fixture
def mock_daemon() -> MagicMock:
    """Fixture providing a mock daemon with an async queue."""
    daemon = MagicMock()
    daemon.queue = AsyncMock()
    # qsize() is a synchronous method on asyncio.Queue
    daemon.queue.qsize = MagicMock(return_value=0)
    daemon.queue.put = AsyncMock()
    return daemon


@pytest.fixture
def app(mock_daemon: MagicMock) -> FastAPI:
    """Fixture creating a test FastAPI app with gateway router and mock daemon attached."""
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    fastapi_app.state.daemon = mock_daemon
    return fastapi_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Fixture providing a TestClient instance bound to the test app."""
    return TestClient(app)


class TestGatewayRoutes:
    """Tests for REST endpoints in gateway routes."""

    def test_health_check(self, client: TestClient, mock_daemon: MagicMock) -> None:
        """Verify GET /v1/health returns online status, active connection metrics, and queue depth."""
        mock_daemon.queue.qsize.return_value = 5

        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["service"] == "Charon Gateway & Core Engine"
        assert data["queue_depth"] == 5
        assert "active_ws_clients" in data
        assert "registered_client_nodes" in data

    def test_submit_task_success(self, client: TestClient, mock_daemon: MagicMock) -> None:
        """Verify POST /v1/task enqueues payload to daemon queue and returns TaskResponse."""
        payload = {
            "prompt": "Inspect logs for anomalies",
            "client_id": "test_client",
            "agent_override": "cleaner",
            "context": {"env": "staging"},
        }

        response = client.post("/v1/task", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"].startswith("task_")
        assert data["status"] == "executing"
        assert data["assigned_agent"] == "cleaner"
        assert data["message"] == "Task accepted and queued for orchestration."

        mock_daemon.queue.put.assert_called_once()
        queued_item = mock_daemon.queue.put.call_args[0][0]
        assert queued_item["prompt"] == "Inspect logs for anomalies"
        assert queued_item["client_id"] == "test_client"
        assert queued_item["agent_override"] == "cleaner"

    def test_respond_to_gatekeeper(self, client: TestClient, mock_daemon: MagicMock) -> None:
        """Verify POST /v1/gatekeeper/respond processes operator authorization command."""
        payload = {
            "approval_id": "appr_9988",
            "decision": "proceed",
            "client_id": "desktop_concierge",
            "notes": "Approved by user",
        }

        response = client.post("/v1/gatekeeper/respond", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "acknowledged",
            "approval_id": "appr_9988",
            "decision": "proceed",
        }

        mock_daemon.queue.put.assert_called_once()
        queued_item = mock_daemon.queue.put.call_args[0][0]
        assert queued_item["task_id"].startswith("gate_")
        assert queued_item["prompt"] == "proceed"
        assert queued_item["client_id"] == "desktop_concierge"


class TestWebSocketEndpoint:
    """Tests for /v1/ws WebSocket authentication and stream lifecycle."""

    def test_websocket_unauthorized_missing_token(self, client: TestClient) -> None:
        """Verify WebSocket connection closes when no API key is provided."""
        with pytest.raises(Exception):
            with client.websocket_connect("/v1/ws"):
                pass

    def test_websocket_unauthorized_invalid_token(self, client: TestClient) -> None:
        """Verify WebSocket connection closes when an invalid API key is provided."""
        with pytest.raises(Exception):
            with client.websocket_connect("/v1/ws?api_key=invalid_secret"):
                pass

    def test_websocket_connect_success_query_token(self, client: TestClient) -> None:
        """Verify WebSocket connection succeeds using query parameter api_key."""
        url = f"/v1/ws?api_key={CHARON_API_KEY}&client_id=node_alpha"
        with client.websocket_connect(url) as websocket:
            data = websocket.receive_json()
            assert data["event_type"] == "status_change"
            assert data["data"]["status"] == "connected"
            assert data["data"]["client_id"] == "node_alpha"

    def test_websocket_connect_success_header_token(self, client: TestClient) -> None:
        """Verify WebSocket connection succeeds using request header api key."""
        headers = {API_KEY_HEADER_NAME.lower(): CHARON_API_KEY}
        url = "/v1/ws?client_id=node_beta"
        with client.websocket_connect(url, headers=headers) as websocket:
            data = websocket.receive_json()
            assert data["event_type"] == "status_change"
            assert data["data"]["status"] == "connected"
            assert data["data"]["client_id"] == "node_beta"
