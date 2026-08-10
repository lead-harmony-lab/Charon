"""
charon/agents/archivist/utils.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Helper utilities for Archivist payload extraction and compatibility wrappers.
Updated to use DynamicActionPayload schema.
"""

from typing import Any, Dict, Union
from charon.intent import DynamicActionPayload
from charon.tools.pdf import chunk_text as _chunk_text  # Backward compatibility re-export


def _get_payload_val(
    payload: Union[DynamicActionPayload, Dict[str, Any], Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """Extracts parameter values seamlessly from either DynamicActionPayload, dict, or arbitrary payload object."""
    if payload is None:
        return default

    if isinstance(payload, DynamicActionPayload):
        # 1. Look inside nested params dict
        if isinstance(payload.params, dict):
            for key in keys:
                if payload.params.get(key) is not None:
                    return payload.params[key]
        # 2. Look directly at attributes on the Pydantic model
        for key in keys:
            val = getattr(payload, key, None)
            if val is not None:
                return val
        return default

    elif isinstance(payload, dict):
        # 1. Look inside 'params' nested sub-dictionary if present
        sub_params = payload.get("params")
        if isinstance(sub_params, dict):
            for key in keys:
                if sub_params.get(key) is not None:
                    return sub_params[key]
        # 2. Look at root level of dict
        for key in keys:
            if payload.get(key) is not None:
                return payload[key]
        return default

    elif hasattr(payload, "model_dump"):
        p_dict = payload.model_dump()
        sub_params = p_dict.get("params")
        if isinstance(sub_params, dict):
            for key in keys:
                if sub_params.get(key) is not None:
                    return sub_params[key]
        for key in keys:
            if p_dict.get(key) is not None:
                return p_dict[key]

    return default