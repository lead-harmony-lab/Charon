"""Plugin entrypoint module for generalist_system_executor."""

import asyncio
import logging
from typing import Any, Dict
import ollama

from charon.agents.generalist.handlers import handle_execute_system_task

logger = logging.getLogger("CHAROND.Skills.GeneralistSystemExecutor")


async def handle_system_task_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous action handler for execute_system_command."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("command", params.get("raw_prompt", ""))

    result = await handle_execute_system_task(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "execute_system_command":
        return asyncio.run(handle_system_task_async(params))

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_system_executor'."
    )