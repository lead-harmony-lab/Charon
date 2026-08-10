"""Plugin entrypoint module for generalist_query_handler."""

import asyncio
import logging
from typing import Any, Dict
import ollama

from charon.agents.generalist.handlers import handle_answer_query

logger = logging.getLogger("CHAROND.Skills.GeneralistQueryHandler")


async def handle_answer_query_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous action handler for answer_query."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("prompt", params.get("raw_prompt", ""))

    result = await handle_answer_query(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def handle_acknowledge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous acknowledgement action handler."""
    return {
        "status": "success",
        "result": "Your directive has been noted. I shall see to the arrangements."
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "answer_query":
        return asyncio.run(handle_answer_query_async(params))
    elif action_name == "acknowledge":
        return handle_acknowledge(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_query_handler'."
    )