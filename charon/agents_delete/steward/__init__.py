"""
charon/agents/steward/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Agent package for home automation and IoT domain.
"""

from typing import Any, Dict
from charon.agents.steward.agent import TheSteward

StewardAgent = TheSteward


def execute_steward_task(payload: Any) -> Dict[str, Any]:
    """Entry point dispatcher for The Steward agent tasks."""
    agent = TheSteward()

    if hasattr(payload, "action"):
        action = payload.action
        params = {
            "target_device": getattr(payload, "target_device", None),
            "command": getattr(payload, "command", None),
            "topic": getattr(payload, "topic", None),
            "payload": getattr(payload, "payload", None),
        }
    elif isinstance(payload, dict):
        action = payload.get("action")
        params = payload
    else:
        return {"status": "error", "message": "Invalid payload format provided."}

    return agent.execute(action=action, params=params)


__all__ = ["TheSteward", "StewardAgent", "execute_steward_task"]