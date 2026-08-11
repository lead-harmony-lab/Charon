"""
Plugin entrypoint module for synthesize.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("Charon.Skills.Synthesize")


def _truncate_context(text: str, max_chars: int = 6000) -> str:
    """Truncates oversized tool outputs from the middle to preserve context window limits."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    truncated_count = len(text) - max_chars
    return (
        f"{text[:half]}\n\n"
        f"[... Charon Skill Guard: Truncated {truncated_count} raw characters ...]\n\n"
        f"{text[-half:]}"
    )


def handle_synthesize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Action handler for synthesizing specialist execution outputs."""
    user_query = params.get("user_query", "")
    raw_output = params.get("raw_output") or params.get("context") or ""
    executing_agent = params.get("executing_agent", "Specialist")

    raw_str = str(raw_output).strip()
    if not raw_str:
        return {
            "status": "success",
            "result": "Task executed successfully with no output returned.",
        }

    sanitized_data = _truncate_context(raw_str, max_chars=6000)

    logger.info(f"[synthesize] Processing output for query context: '{user_query[:40]}...'")

    return {
        "status": "success",
        "result": sanitized_data,
        "agent": executing_agent,
        "raw_character_count": len(raw_str),
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "synthesize":
        return handle_synthesize(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'synthesize'.")