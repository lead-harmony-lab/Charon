"""Plugin entrypoint module for generalist_math_evaluator."""

import asyncio
import logging
from typing import Any, Dict
import ollama

from charon.agents.generalist.handlers import handle_calculate_math

logger = logging.getLogger("CHAROND.Skills.GeneralistMathEvaluator")


async def handle_math_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous action handler for calculate_math."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("expression", params.get("raw_prompt", ""))

    result = await handle_calculate_math(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "calculate_math":
        return asyncio.run(handle_math_async(params))

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_math_evaluator'."
    )