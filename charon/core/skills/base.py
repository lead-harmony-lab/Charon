"""
charon/core/skills/base.py
System Version: v0.7.0 | File Revision: 7.0.0

Module: Abstract Base Class defining the contract for in-memory and dynamic skill plugins.
Establishes clean separation between code identity (skill_id) and prompt contract (action_name),
aligned with CBAC Schema V2 capability architecture and quarantine lifecycle management.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class BaseSkill(ABC):
    """Abstract Base Class for in-memory and modular Charon Skill Plugins."""

    # Unique code instance identifier (e.g., 'sk_slack_send_msg_v1')
    skill_id: str = "sk_unnamed_skill"

    # Action contract trigger name invoked by LLMs / Routers (e.g., 'send_slack_message')
    action_name: str = "unnamed_action"

    version: str = "1.0.0"
    category: str = "General"
    description: str = "Standard dynamic skill plugin."

    # Internal Python callable/method name inside the skill module
    handler_name: str = "execute"

    # Status state machine: 'ACTIVE', 'QUARANTINED', 'DISABLED'
    status: str = "ACTIVE"
    quarantine_reason: Optional[str] = None

    # Restrict checkout to specific agent IDs, or ["*"] for global availability
    allowed_agents: List[str] = ["*"]
    is_global: bool = False

    # Primitive permissions required by CBAC Schema V2
    required_permissions: List[str] = []

    system_requirements: List[str] = []
    consumed_artifacts: List[str] = []
    produced_artifacts: List[str] = []

    @abstractmethod
    def execute(
        self, agent_name: str, parameters: Dict[str, Any], raw_prompt: str = ""
    ) -> Union[str, Dict[str, Any]]:
        """Executes the skill logic given the agent identity and parameter payload."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serializes skill metadata for indexing into skill_registry under CBAC Schema V2."""
        return {
            "skill_id": self.skill_id,
            "action_name": self.action_name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "handler_name": self.handler_name,
            "status": self.status,
            "quarantine_reason": self.quarantine_reason,
            "allowed_agents": self.allowed_agents,
            "is_global": 1 if self.is_global else 0,
            "required_permissions": self.required_permissions,
            "system_requirements": self.system_requirements,
            "consumed_artifacts": self.consumed_artifacts,
            "produced_artifacts": self.produced_artifacts,
        }