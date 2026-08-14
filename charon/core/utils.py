"""
charon/core/utils.py
System Version: v0.4.0 | File Revision: 4.0.0

Module: Utility routines for payload sanitization, role normalization,
and defensive Pydantic schema extraction for Work Contract execution envelopes.
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger("Charon.Core.Utils")


def clean_json_string(raw_str: str) -> str:
    """
    Safely extracts and cleans raw JSON strings from LLM responses.
    Utilized by the BaseWorkContract Diff Engine as a defensive fallback
    for salvaging payloads prior to strict Pydantic validation.
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


def normalize_role_name(role_name: Any) -> str:
    """
    Sanitizes and normalizes raw system role identifiers.
    Ensures safe SSOT resolution when querying the SkillLibrarian.
    """
    if not role_name:
        return ""

    role_str = str(role_name).strip()

    # Strip quotes, brackets, angle brackets, and markdown backticks
    role_str = re.sub(r"^[`'\"\[\(<]+|[`'\"\]\)>]+$", "", role_str).strip()

    # Strip common LLM artifact prefixes (e.g., 'role:')
    if role_str.lower().startswith(("role:", "agent:")):
        role_str = role_str.split(":", 1)[1].strip()

    return role_str.lower()


def get_schema_json(schema_class: type) -> Dict[str, Any]:
    """
    Defensively retrieves JSON schema dict from payload classes.
    Critical for dynamically injecting the BaseWorkContract's expected
    artifact_schema into the LLM context window.
    """
    if not schema_class:
        return {}

    try:
        # Prioritize Pydantic v2
        if hasattr(schema_class, "model_json_schema") and callable(
            getattr(schema_class, "model_json_schema")
        ):
            return schema_class.model_json_schema()

        # Custom extraction override
        if hasattr(schema_class, "get_clean_schema") and callable(
            getattr(schema_class, "get_clean_schema")
        ):
            return schema_class.get_clean_schema()

        # Fallback to Pydantic v1
        if hasattr(schema_class, "schema") and callable(
            getattr(schema_class, "schema")
        ):
            return schema_class.schema()

    except Exception as e:
        logger.warning(f"[UTILS] Failed to extract schema from {schema_class}: {e}")

    return {}