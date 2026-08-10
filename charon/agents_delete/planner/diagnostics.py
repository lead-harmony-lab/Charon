"""
charon/agents/planner/diagnostics.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Error matrix parsing and failure diagnosis.
"""

import logging
from typing import Any, Callable, Dict, Optional, Union

import ollama

from charon.agents.planner.constants import DIAGNOSTICS_SYSTEM_PROMPT
from charon.agents.planner.utils import resolve_log_content
from charon.intent import DynamicActionPayload

logger = logging.getLogger("Charon.Planner.Diagnostics")


async def analyze_error_logs(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Parses complex compilation or system logs to diagnose failures."""
    log_content = resolve_log_content(
        params, raw_prompt=raw_prompt, payload=payload
    )
    if not log_content:
        return "Error: 'log_content' is required for analysis."

    logger.info("The Planner is analyzing the provided error matrix...")

    try:
        analysis = ""
        if stream_callback:
            async for chunk in await client.generate(
                model=model_name,
                system=DIAGNOSTICS_SYSTEM_PROMPT,
                prompt=f"Log Content:\n{log_content}",
                stream=True,
            ):
                token = chunk.get("response", "")
                analysis += token
                stream_callback(token)
        else:
            response = await client.generate(
                model=model_name,
                system=DIAGNOSTICS_SYSTEM_PROMPT,
                prompt=f"Log Content:\n{log_content}",
            )
            analysis = response.get("response", "").strip()

        return f"Log Analysis:\n\n{analysis.strip()}"
    except Exception as e:
        logger.error(f"Inference failure during log analysis: {e}")
        return f"Failed to analyze the error matrix due to inference engine failure: {str(e)}"