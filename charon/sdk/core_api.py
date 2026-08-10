"""
charon/sdk/core_api.py
System Version: v0.1.0 | File Revision: 2.0.0

Mixin for core engine REST operations (Task submission, Gatekeeper, Health).
"""

from typing import Any, Dict, Literal, Optional
import httpx

from charon.sdk.models import GatekeeperDecision, TaskRequest, TaskResponse, dump_model


class CoreApiMixin:
    """Provides methods for basic daemon status, task dispatching, and operator approvals."""

    _http_client: Optional[httpx.AsyncClient]
    client_id: str
    auto_discover_hardware: bool
    default_context: Dict[str, Any]

    def _get_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            raise RuntimeError("SDK client not connected. Call `await node.connect()` first.")
        return self._http_client

    def refresh_telemetry(self) -> Dict[str, Any]:
        """Declared in main client node."""
        raise NotImplementedError

    async def check_health(self) -> Dict[str, Any]:
        """Queries engine health status endpoint."""
        client = self._get_client()
        response = await client.get("/v1/health")
        response.raise_for_status()
        return response.json()

    async def get_connected_clients(self) -> Dict[str, Any]:
        """Queries engine for active connected peripheral nodes."""
        client = self._get_client()
        response = await client.get("/v1/clients")
        response.raise_for_status()
        return response.json()

    async def submit_task(
        self,
        prompt: str,
        agent_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskResponse:
        """Submits a prompt or command to Charon for triage and orchestration."""
        client = self._get_client()

        if self.auto_discover_hardware:
            self.refresh_telemetry()

        merged_context = {**self.default_context, **(context or {})}

        request_payload = TaskRequest(
            prompt=prompt,
            client_id=self.client_id,
            agent_override=agent_override,
            context=merged_context,
        )

        response = await client.post(
            "/v1/task",
            json=dump_model(request_payload),
        )
        response.raise_for_status()
        return TaskResponse(**response.json())

    async def respond_gatekeeper(
        self,
        approval_id: str,
        decision: Literal["proceed", "rescind", "cancel"],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submits an operator authorization decision in response to a Gatekeeper intercept."""
        client = self._get_client()

        decision_payload = GatekeeperDecision(
            approval_id=approval_id,
            decision=decision,
            client_id=self.client_id,
            notes=notes,
        )

        response = await client.post(
            "/v1/gatekeeper/respond",
            json=dump_model(decision_payload),
        )
        response.raise_for_status()
        return response.json()