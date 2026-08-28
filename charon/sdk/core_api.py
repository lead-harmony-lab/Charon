import json
from typing import Any, Dict, Literal, Optional
import httpx


class CoreApiMixin:
    """Provides methods for basic daemon status, task dispatching, and operator approvals via WebSocket."""

    _http_client: Optional[httpx.AsyncClient]
    _ws_client: Optional[Any]  # Active WebSocket connection maintained by the main client node
    client_id: str
    auto_discover_hardware: bool
    default_context: Dict[str, Any]

    def _get_http_client(self) -> httpx.AsyncClient:
        if not getattr(self, "_http_client", None):
            raise RuntimeError("SDK HTTP client not connected. Call `await node.connect()` first.")
        return self._http_client

    def _get_ws_client(self) -> Any:
        if not getattr(self, "_ws_client", None):
            raise RuntimeError("SDK WebSocket client not connected. Call `await node.connect()` first.")
        return self._ws_client

    def refresh_telemetry(self) -> Dict[str, Any]:
        """Declared in main client node."""
        raise NotImplementedError

    async def check_health(self) -> Dict[str, Any]:
        """Queries engine health status endpoint via HTTP."""
        client = self._get_http_client()
        response = await client.get("/v1/health")
        response.raise_for_status()
        return response.json()

    async def get_connected_clients(self) -> Dict[str, Any]:
        """Queries engine for active connected peripheral nodes via HTTP."""
        client = self._get_http_client()
        response = await client.get("/v1/clients")
        response.raise_for_status()
        return response.json()

    async def submit_task(
        self,
        prompt: str,
        agent_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Pushes a task to Charon for orchestration via WebSocket."""
        if self.auto_discover_hardware:
            self.refresh_telemetry()

        merged_context = {**self.default_context, **(context or {})}

        payload = {
            "action": "submit_task",
            "client_id": self.client_id,
            "prompt": prompt,
            "agent_override": agent_override,
            "context": merged_context
        }

        ws = self._get_ws_client()
        await ws.send(json.dumps(payload))

    async def respond_gatekeeper(
        self,
        approval_id: str,
        decision: Literal["proceed", "rescind", "cancel"],
        notes: Optional[str] = None,
    ) -> None:
        """Submits an operator authorization decision via WebSocket."""
        payload = {
            "action": "gatekeeper_respond",
            "client_id": self.client_id,
            "approval_id": approval_id,
            "decision": decision,
            "notes": notes or ""
        }

        ws = self._get_ws_client()
        await ws.send(json.dumps(payload))