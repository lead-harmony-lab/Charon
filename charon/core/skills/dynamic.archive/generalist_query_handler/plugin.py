"""Plugin entrypoint module for generalist_query_handler."""

import asyncio
import logging
from typing import Any, Dict, Union, Coroutine
import ollama

logger = logging.getLogger("CHAROND.Skills.GeneralistQueryHandler")


async def handle_answer_query_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous action handler for answer_query using Ollama."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")

    # Safeguard prompt extraction across common key variants
    raw_prompt = (
        params.get("prompt")
        or params.get("raw_prompt")
        or params.get("query")
        or ""
    )

    if not raw_prompt:
        logger.warning("[GeneralistQueryHandler] 'answer_query' called with empty prompt parameters.")
        return {
            "status": "error",
            "message": "Missing required 'prompt', 'raw_prompt', or 'query' parameter.",
        }

    try:
        logger.info(f"[GeneralistQueryHandler] Dispatching query to Ollama (model: '{model_name}')...")
        response = await client.generate(model=model_name, prompt=raw_prompt)
        result_text = response.get("response", "")

        return {
            "status": "success",
            "result": result_text,
        }
    except Exception as e:
        logger.error(f"[GeneralistQueryHandler] Generation failed via Ollama: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Ollama execution fault: {str(e)}",
        }


def handle_answer_query(params: Dict[str, Any]) -> Union[Dict[str, Any], Coroutine]:
    """
    Entrypoint matching DB handler_name column.
    Safely bridges sync and async contexts.
    """
    try:
        # Check if we are already inside a running event loop (e.g., Charon Daemon)
        loop = asyncio.get_running_loop()
        # Return the unawaited coroutine for the SkillExecutorMixin to await
        return handle_answer_query_async(params)
    except RuntimeError:
        # No running event loop (e.g., standalone CLI testing), safe to use asyncio.run
        return asyncio.run(handle_answer_query_async(params))


def handle_acknowledge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous acknowledgement action handler."""
    return {
        "status": "success",
        "result": "Your directive has been noted. I shall see to the arrangements.",
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Union[Dict[str, Any], Coroutine]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "answer_query":
        return handle_answer_query(params)
    elif action_name == "acknowledge":
        return handle_acknowledge(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_query_handler'."
    )