"""
charon/sdk/router_api.py
System Version: v0.1.0 | File Revision: 2.0.0

Mixin for Dynamic Router Control Panel REST API interactions.
"""

from typing import Any, Dict, List, Optional
import httpx


class RouterApiMixin:
    """Provides methods to inspect and dynamically tune routing priorities, tools, and shortcuts."""

    _http_client: Optional[httpx.AsyncClient]

    def _get_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            raise RuntimeError("SDK client not connected. Call `await node.connect()` first.")
        return self._http_client

    async def get_router_agents(self) -> Dict[str, Any]:
        """Retrieves registered agents, capability descriptions, priority weights, and active tools."""
        client = self._get_client()
        response = await client.get("/v1/router/agents")
        response.raise_for_status()
        return response.json()

    async def update_agent_bias(
        self,
        agent_id: str,
        description: Optional[str] = None,
        priority_weight: Optional[float] = None,
        override_triggers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Dynamically updates an agent's description, priority weight multiplier, or triggers."""
        client = self._get_client()

        payload: Dict[str, Any] = {}
        if description is not None:
            payload["description"] = description
        if priority_weight is not None:
            payload["priority_weight"] = priority_weight
        if override_triggers is not None:
            payload["override_triggers"] = override_triggers

        response = await client.put(
            f"/v1/router/agents/{agent_id}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def set_agent_tool_status(
        self, agent_id: str, tool_name: str, enabled: bool
    ) -> Dict[str, Any]:
        """Enables or disables a specific tool for an agent at runtime."""
        client = self._get_client()
        payload = {"tool_name": tool_name, "enabled": enabled}
        response = await client.patch(
            f"/v1/router/agents/{agent_id}/tools",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def get_override_rules(self) -> Dict[str, Any]:
        """Retrieves all dynamic shortcut override rules."""
        client = self._get_client()
        response = await client.get("/v1/router/rules")
        response.raise_for_status()
        return response.json()

    async def add_override_rule(
        self, trigger: str, target_agent: str, description: str = ""
    ) -> Dict[str, Any]:
        """Creates a new dynamic shortcut override rule."""
        client = self._get_client()
        payload = {
            "trigger": trigger,
            "target_agent": target_agent,
            "description": description,
        }
        response = await client.post(
            "/v1/router/rules",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def delete_override_rule(self, rule_id: str) -> Dict[str, Any]:
        """Deletes a dynamic shortcut override rule by ID."""
        client = self._get_client()
        response = await client.delete(f"/v1/router/rules/{rule_id}")
        response.raise_for_status()
        return response.json()

    async def get_triage_logs(self, limit: int = 50) -> Dict[str, Any]:
        """Fetches recent Pass 1 triage evaluation decisions."""
        client = self._get_client()
        response = await client.get(
            "/v1/router/triage/logs", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()