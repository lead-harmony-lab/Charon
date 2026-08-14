"""
charon/intent/payloads/dynamic.py
System Version: v0.1.0 | File Revision: 1.1.0

Universal payload wrapper for dynamic skill execution.
Replaces static compile-time Pydantic models with runtime schema validation.
"""

from typing import Any, Dict
from pydantic import Field

from charon.intent.base import BaseAgentPayload
from charon.core.skills import SkillLibrarian


class DynamicActionPayload(BaseAgentPayload):
    """
    Universal payload for executing any dynamic skill in the registry.
    Bypasses static Pydantic constraints in favor of SQLite schema validation.
    """

    call_action: str = Field(
        ...,
        description="The specific action_name to invoke (e.g., 'list_tasks', 'fetch_datasheet')"
    )
    thought: str = Field(
        default="",
        description="The agent's internal reasoning or plan for calling this tool"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value arguments matching the action's parameter schema"
    )

    def validate_against_manifest(self) -> bool:
        """
        Dynamically checks if required parameters match the JSON Schema stored in the SQLite registry.
        Raises ValueError if required parameters are missing.
        """
        librarian = SkillLibrarian.get_instance()
        action_details = librarian.get_action_details(self.call_action)

        if not action_details:
            default_action = (
                librarian.get_default_action_for_role("system_generalist")
                if hasattr(librarian, "get_default_action_for_role")
                else ""
            )
            # Fallback check for raw conversational routing (no specific tool)
            if default_action and self.call_action == default_action:
                return True
            raise ValueError(f"Action '{self.call_action}' is not indexed in the Librarian.")

        schema_params = action_details.get("parameters", {})
        required_params = schema_params.get("required", [])

        for param in required_params:
            if param not in self.params:
                raise ValueError(
                    f"Missing required parameter '{param}' for action '{self.call_action}'. "
                    f"Expected schema: {schema_params}"
                )

        return True