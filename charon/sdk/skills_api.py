"""
charon/sdk/skills_api.py
System Version: v0.1.0 | File Revision: 2.0.0

Mixin for Skill Forge Human-in-the-Loop REST API interactions.
"""

from typing import Any, Dict
import httpx


class SkillForgeApiMixin:
    """Provides methods for querying skill gaps, blueprints, and registering forged skills."""

    _http_client: Optional[httpx.AsyncClient]

    def _get_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            raise RuntimeError("SDK client not connected. Call `await node.connect()` first.")
        return self._http_client

    async def get_skill_gaps(self) -> Dict[str, Any]:
        """Queries tracked skill diagnostic gaps and frequency metrics."""
        client = self._get_client()
        response = await client.get("/v1/skills/gaps")
        response.raise_for_status()
        return response.json()

    async def get_skill_blueprints(self) -> Dict[str, Any]:
        """Queries pending SkillBlueprint artifacts waiting for human-in-the-loop forging."""
        client = self._get_client()
        response = await client.get("/v1/skills/blueprints")
        response.raise_for_status()
        return response.json()

    async def get_gemini_prompt(self, action_name: str) -> Dict[str, Any]:
        """Retrieves formatted copy-paste Gemini prompt for a specific missing action blueprint."""
        client = self._get_client()
        response = await client.get(
            f"/v1/skills/blueprints/{action_name}/prompt"
        )
        response.raise_for_status()
        return response.json()

    async def reset_skill_gap(self, action_name: str) -> Dict[str, Any]:
        """Resets gap tracking failure counter and pending blueprint for a specific action."""
        client = self._get_client()
        response = await client.delete(
            f"/v1/skills/gaps/{action_name}"
        )
        response.raise_for_status()
        return response.json()

    async def register_skill(
        self,
        skill_name: str,
        action_name: str,
        code: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """Registers generated Python skill code back into the system."""
        client = self._get_client()
        payload = {
            "skill_name": skill_name,
            "action_name": action_name,
            "code": code,
            "description": description,
        }
        response = await client.post(
            "/v1/skills/register", json=payload
        )
        response.raise_for_status()
        return response.json()