"""
charon/agents/planner/sequencing.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Blueprint generation for multi-step engineering sequences.
"""

import logging
from typing import Any, Callable, Dict, Optional, Union

import ollama

from charon.agents.planner.constants import BUILD_SEQUENCE_SYSTEM_PROMPT
from charon.agents.planner.utils import resolve_objective
from charon.intent import DynamicActionPayload

logger = logging.getLogger("Charon.Planner.Sequencing")


async def draft_build_sequence(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Generates a structured multi-step engineering blueprint based on high-level goals."""
    objective = resolve_objective(params, raw_prompt=raw_prompt, payload=payload)
    if not objective:
        return "Error: An 'objective' parameter is required to draft a sequence."

    logger.info(f"The Planner is strategizing the objective: {objective}")

    try:
        plan_response = ""
        if stream_callback:
            async for chunk in await client.generate(
                model=model_name,
                system=BUILD_SEQUENCE_SYSTEM_PROMPT,
                prompt=f"Objective: {objective}",
                stream=True,
            ):
                token = chunk.get("response", "")
                plan_response += token
                stream_callback(token)
        else:
            response = await client.generate(
                model=model_name,
                system=BUILD_SEQUENCE_SYSTEM_PROMPT,
                prompt=f"Objective: {objective}",
            )
            plan_response = response.get("response", "").strip()

        return plan_response.strip()

    except Exception as e:
        logger.error(f"Inference failure during planning: {e}")
        return f"The inference engine is currently unable to draft sequences: {str(e)}"