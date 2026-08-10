from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.middleware import APIKeyMiddleware


def create_app(public_paths=None) -> FastAPI:
    """Helper factory creating a test FastAPI instance with APIKeyMiddleware attached."""
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, public_paths=public_paths)

    @app.get("/v1/health")
    async def health_endpoint():
        return {"status": "healthy"}

    @app.get("/v1/protected")
    async def protected_endpoint():
        return {"data": "classified"}

    @app.get("/custom-open")
    async def custom_open_endpoint():
        return {"data": "public"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):  # <--- Added WebSocket type hint here
        await websocket.accept()
        await websocket.send_json({"msg": "connected"})
        await websocket.close()

    return app


class TestAPIKeyMiddleware:
    """Tests for APIKeyMiddleware HTTP authentication and route protection."""

    def test_default_public_paths_allowed(self) -> None:
        """Verify default public paths bypass API key verification."""
        client = TestClient(create_app())
        response = client.get("/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_protected_path_missing_api_key(self) -> None:
        """Verify protected path returns 401 when API key header is missing."""
        client = TestClient(create_app())
        response = client.get("/v1/protected")

        assert response.status_code == 401
        assert response.json() == {
            "detail": f"Invalid or missing API Key header ('{API_KEY_HEADER_NAME}')."
        }

    def test_protected_path_invalid_api_key(self) -> None:
        """Verify protected path returns 401 when provided API key is invalid."""
        client = TestClient(create_app())
        headers = {API_KEY_HEADER_NAME: "invalid-key-secret"}
        response = client.get("/v1/protected", headers=headers)

        assert response.status_code == 401
        assert response.json() == {
            "detail": f"Invalid or missing API Key header ('{API_KEY_HEADER_NAME}')."
        }

    def test_protected_path_valid_api_key(self) -> None:
        """Verify protected path returns 200 when correct API key is provided."""
        client = TestClient(create_app())
        headers = {API_KEY_HEADER_NAME: CHARON_API_KEY}
        response = client.get("/v1/protected", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"data": "classified"}

    def test_custom_public_paths(self) -> None:
        """Verify custom public_paths override standard defaults without authentication."""
        app = create_app(public_paths=["/custom-open"])
        client = TestClient(app)

        # Custom path works without API Key
        response = client.get("/custom-open")
        assert response.status_code == 200
        assert response.json() == {"data": "public"}

        # Default paths are no longer public when overridden
        health_response = client.get("/v1/health")
        assert health_response.status_code == 401

    def test_websocket_bypasses_middleware(self) -> None:
        """Verify WebSocket connections bypass HTTP API key middleware check."""
        client = TestClient(create_app())
        with client.websocket_connect("/ws") as websocket:
            data = websocket.receive_json()
            assert data == {"msg": "connected"}

    def test_unauthorized_attempt_logs_warning(self) -> None:
        """Verify unauthorized access logs a warning with client IP information."""
        client = TestClient(create_app())

        with patch("charon.gateway.middleware.logger") as mock_logger:
            response = client.get("/v1/protected")
            assert response.status_code == 401

            mock_logger.warning.assert_called_once()
            log_msg = mock_logger.warning.call_args[0][0]
            assert "Unauthorized HTTP access attempt" in log_msg
