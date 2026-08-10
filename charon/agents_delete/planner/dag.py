"""
charon/agents/planner/dag.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Task decomposition into structured DAG execution sequences.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

import ollama

from charon.agents.planner.constants import DAG_SYSTEM_PROMPT
from charon.agents.planner.utils import resolve_objective
from charon.intent import DynamicActionPayload

logger = logging.getLogger("Charon.Planner.DAG")


async def decompose_task(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Decomposes a user request into a structured sequence of agent execution steps."""
    objective = resolve_objective(params, raw_prompt=raw_prompt, payload=payload)
    if not objective:
        logger.warning("No objective provided for task decomposition.")
        return []

    logger.info(
        f"The Planner is decomposing user objective into execution DAG: {objective}"
    )

    try:
        response = await client.generate(
            model=model_name,
            system=DAG_SYSTEM_PROMPT,
            prompt=f"Objective: {objective}",
            format="json",
        )
        raw_response = response.get("response", "[]").strip()

        if "```" in raw_response:
            match = re.search(
                r"```(?:json)?\s*(.*?)\s*```", raw_response, re.DOTALL
            )
            if match:
                raw_response = match.group(1).strip()

        plan = json.loads(raw_response)
        return plan if isinstance(plan, list) else []
    except Exception as e:
        logger.error(f"Failed to parse decomposition plan: {e}")
        return []