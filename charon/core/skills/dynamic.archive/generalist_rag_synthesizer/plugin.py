"""Plugin entrypoint module for generalist_rag_synthesizer."""

import asyncio
import logging
from typing import Any, Dict
import ollama

from charon.agents.generalist.handlers import handle_synthesize_rag

logger = logging.getLogger("CHAROND.Skills.GeneralistRAGSynthesizer")


async def handle_rag_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous action handler for synthesize_rag."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("query", params.get("raw_prompt", ""))

    result = await handle_synthesize_rag(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "synthesize_rag":
        return asyncio.run(handle_rag_async(params))

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'generalist_rag_synthesizer'."
    )