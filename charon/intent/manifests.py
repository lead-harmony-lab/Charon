"""
charon/intent/manifests.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Agent capability manifests and prompt formatting helpers.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from charon.config.paths import STATE_DB_PATH
from charon.core.skills import SkillLibrarian
from charon.db.repositories import AgentRepository


class AgentManifest(BaseModel):
    """Dynamic metadata representing an agent's capabilities and routing attributes."""
    agent_id: str
    display_name: str
    description: str = ""
    default_action: str = ""
    priority_weight: float = Field(default=1.0, ge=0.0)
    override_triggers: List[str] = Field(default_factory=list)
    active_tools: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    risk_level: int = Field(default=0, ge=0, le=3)


def get_agent_manifest(
    agent_id: str,
    repo: Optional[AgentRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> Optional[AgentManifest]:
    """Retrieves validated agent capabilities using the repository pattern."""
    repo = repo or AgentRepository(db_path)
    agent_data = repo.get_active_agent(agent_id)

    if not agent_data:
        return None

    librarian = SkillLibrarian.get_instance(db_path)

    raw_default = agent_data.get("default_action")
    if raw_default:
        default_action = raw_default
    elif hasattr(librarian, "get_default_action_for_role"):
        default_action = librarian.get_default_action_for_role("system_generalist") or ""
    else:
        default_action = ""

    raw_triggers = agent_data.get("override_triggers", [])
    if isinstance(raw_triggers, str):
        triggers = json.loads(raw_triggers or "[]")
    else:
        triggers = raw_triggers or []

    raw_tools = agent_data.get("active_tools", [])
    if isinstance(raw_tools, str):
        tools = json.loads(raw_tools or "[]")
    else:
        tools = raw_tools or []

    return AgentManifest(
        agent_id=agent_data["agent_id"],
        display_name=agent_data["display_name"],
        description=agent_data.get("description", ""),
        default_action=default_action,
        priority_weight=float(agent_data.get("priority_weight", 1.0)),
        override_triggers=triggers,
        active_tools=tools,
        risk_level=agent_data.get("risk_level", 0),
        is_active=bool(agent_data.get("is_active", 1)),
    )


def get_triage_agent_descriptions(
    repo: Optional[AgentRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """Generates formatted agent capabilities for LLM triage prompts."""
    repo = repo or AgentRepository(db_path)
    librarian = SkillLibrarian.get_instance(db_path)
    lines = []

    active_agents = repo.get_all_active_agents()

    for agent in active_agents:
        agent_id = agent["agent_id"]

        # Delegate dynamic action discovery to the Librarian
        if hasattr(librarian, "list_available_actions"):
            agent_actions = librarian.list_available_actions(agent_id)
        else:
            agent_actions = []

        caps = ", ".join(agent_actions) if agent_actions else "No active dynamic skills"

        lines.append(
            f"- **{agent['display_name']}** (`{agent_id}`): "
            f"{agent.get('description', '')} Capabilities: [{caps}]"
        )

    return "\n".join(lines)