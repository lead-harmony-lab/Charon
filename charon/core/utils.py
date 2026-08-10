"""
charon/core/utils.py
System Version: v0.3.3 | File Revision: 3.0.0

Module: Utility routines for JSON sanitization, dynamic agent ID normalization,
and defensive Pydantic schema extraction adhering to the Janitorial Working Anchor.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Core.Utils")


def clean_json_string(raw_str: str) -> str:
    """
    Safely extracts and cleans raw JSON strings (objects or arrays) from LLM responses.
    Handles markdown code blocks, greedy fence artifacts, and trailing commas.
    """
    if not raw_str:
        return ""

    raw_str = raw_str.strip()

    # 1. Strip markdown code fences if present (non-greedy)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_str, re.IGNORECASE)
    if fence_match:
        raw_str = fence_match.group(1).strip()
    else:
        # 2. Extract outermost JSON object {} or array [] structure
        bracket_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw_str)
        if bracket_match:
            raw_str = bracket_match.group(1).strip()

    # 3. Clean trailing commas before closing braces or brackets
    raw_str = re.sub(r",\s*([\}\]])", r"\1", raw_str)

    return raw_str


def normalize_agent_id(agent: Any) -> str:
    """
    Sanitizes and normalizes raw agent/role identifier strings.
    Strips surrounding quotes, markdown formatting, brackets, and LLM prefixes.
    """
    if not agent:
        return ""

    agent_str = str(agent).strip()

    # Strip quotes, brackets, angle brackets, and markdown backticks
    agent_str = re.sub(r"^[`'\"\[\(<]+|[`'\"\]\)>]+$", "", agent_str).strip()

    # Strip common LLM artifact prefixes (e.g., 'agent:', 'role:')
    if agent_str.lower().startswith(("agent:", "role:")):
        agent_str = agent_str.split(":", 1)[1].strip()

    return agent_str.lower()


def normalize_agent(agent: Any) -> str:
    """Backward-compatible function returning a sanitized string agent identifier."""
    return normalize_agent_id(agent)


def get_schema_json(schema_class: type) -> Dict[str, Any]:
    """
    Defensively retrieves JSON schema dict from payload classes across Pydantic versions.
    Fallback chain: custom get_clean_schema() -> Pydantic v2 model_json_schema() -> Pydantic v1 schema().
    """
    if not schema_class:
        return {}

    try:
        if hasattr(schema_class, "get_clean_schema") and callable(
            getattr(schema_class, "get_clean_schema")
        ):
            return schema_class.get_clean_schema()

        if hasattr(schema_class, "model_json_schema") and callable(
            getattr(schema_class, "model_json_schema")
        ):
            return schema_class.model_json_schema()

        if hasattr(schema_class, "schema") and callable(
            getattr(schema_class, "schema")
        ):
            return schema_class.schema()
    except Exception as e:
        logger.warning(f"[UTILS] Failed to extract schema from {schema_class}: {e}")

    return {}