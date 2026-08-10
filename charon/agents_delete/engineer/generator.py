"""
charon/agents/engineer/generator.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Domain handler for standalone script drafting without execution.
Updated for DynamicActionPayload intent parsing.
"""

import logging
from typing import Any, Dict, Optional, Union
import ollama

from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Engineer.Generator")


async def handle_generate_script_only(
    client: ollama.AsyncClient,
    model_name: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
) -> str:
    """Drafts a Python script without auto-executing it."""
    params = params or {}
    p_params = getattr(payload, "params", {}) if isinstance(getattr(payload, "params", None), dict) else {}

    task = (
        getattr(payload, "prompt", None)
        or getattr(payload, "problem", None)
        or (payload.get("prompt") if isinstance(payload, dict) else None)
        or (payload.get("problem") if isinstance(payload, dict) else None)
        or p_params.get("prompt")
        or p_params.get("problem")
        or p_params.get("task")
        or params.get("prompt")
        or params.get("problem")
        or params.get("task")
        or raw_prompt
    )
    if not task or not str(task).strip():
        return "Error: A 'prompt' or 'task' parameter is required."

    system_prompt = (
        "You are an expert Python software engineer. Write a clean, self-contained, "
        "production-grade Python script to fulfill the objective."
    )

    try:
        response = await client.generate(
            model=model_name,
            system=system_prompt,
            prompt=f"Task: {task}",
        )
        return response.get("response", "").strip()
    except Exception as e:
        logger.error(f"Failed to generate script: {e}")
        return f"Error during script generation: {e}"