"""Plugin entrypoint module for generalist_system_inspector."""

import asyncio
import logging
from typing import Any, Dict

from charon.agents.generalist.handlers import handle_get_system_info

logger = logging.getLogger("CHAROND.Skills.GeneralistSystemInspector")


async def handle_sys_info_async() -> Dict[str, Any]:
    """Asynchronous action handler for system_info."""
    result = await handle_get_system_info()
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "system_info":
        return asyncio.run(handle_sys_info_async())

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_system_inspector'."
    )