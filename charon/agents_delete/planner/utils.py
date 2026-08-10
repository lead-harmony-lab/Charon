"""
charon/agents/planner/utils.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Helper utilities for Planner domain payload extraction.
"""

from typing import Any, Dict, Optional, Union

from charon.intent import DynamicActionPayload


def _extract_param_dict(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]]
) -> Dict[str, Any]:
    if isinstance(payload, DynamicActionPayload):
        return payload.params or {}
    elif isinstance(payload, dict):
        return payload
    return {}


def resolve_objective(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Extracts the target objective from payload, params, or raw_prompt."""
    p_dict = _extract_param_dict(payload)

    obj = (
        p_dict.get("objective")
        or p_dict.get("task")
        or p_dict.get("goal")
        or getattr(payload, "objective", None)
        or getattr(payload, "task", None)
        or getattr(payload, "goal", None)
        or params.get("objective")
        or params.get("task")
        or params.get("goal")
    )
    if obj:
        return str(obj).strip()

    return raw_prompt.strip() if raw_prompt else ""


def resolve_log_content(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Extracts error/log content from payload, params, or raw_prompt."""
    p_dict = _extract_param_dict(payload)

    log_data = (
        p_dict.get("log_content")
        or p_dict.get("logs")
        or p_dict.get("error_log")
        or getattr(payload, "log_content", None)
        or getattr(payload, "logs", None)
        or params.get("log_content")
        or params.get("logs")
        or params.get("error_log")
    )
    if log_data:
        return str(log_data).strip()

    return raw_prompt.strip() if raw_prompt else ""


def resolve_code_prompt(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Extracts code generation prompt/intent from payload, params, or raw_prompt."""
    p_dict = _extract_param_dict(payload)

    code_p = (
        p_dict.get("prompt")
        or p_dict.get("intent")
        or p_dict.get("task")
        or getattr(payload, "prompt", None)
        or getattr(payload, "intent", None)
        or params.get("prompt")
        or params.get("intent")
        or params.get("task")
    )
    if code_p:
        return str(code_p).strip()

    return raw_prompt.strip() if raw_prompt else ""