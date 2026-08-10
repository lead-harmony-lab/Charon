"""
charon/agents/cleaner/utils.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Internal helper utilities for The Cleaner agent package.
Updated for DynamicActionPayload integration and nested parameter extraction.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from charon.config.paths import resolve_project_path
from charon.intent import DynamicActionPayload


def get_param(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any], Any]],
    params: Optional[Dict[str, Any]],
    attr_name: str,
    *alt_keys: str,
    default: Any = None,
) -> Any:
    """Helper to safely retrieve a parameter from a payload object, nested dicts, or parameter dictionary."""
    params = params or {}
    keys_to_check = (attr_name, *alt_keys)

    if payload is not None:
        # 1. Check inside nested payload.params dict if using DynamicActionPayload
        p_params = getattr(payload, "params", None)
        if isinstance(p_params, dict):
            for key in keys_to_check:
                if p_params.get(key) is not None:
                    return p_params[key]

        # 2. Check direct payload model attributes
        for key in keys_to_check:
            if hasattr(payload, key):
                val = getattr(payload, key, None)
                if val is not None:
                    return val

        # 3. If payload itself is a dict, check it directly
        if isinstance(payload, dict):
            sub_params = payload.get("params")
            if isinstance(sub_params, dict):
                for key in keys_to_check:
                    if sub_params.get(key) is not None:
                        return sub_params[key]
            for key in keys_to_check:
                if payload.get(key) is not None:
                    return payload[key]

    # 4. Check explicit params dictionary passed into function
    for key in keys_to_check:
        if key in params and params[key] is not None:
            return params[key]

    return default


def resolve_target_workspace(
    base_path_str: Optional[str] = None,
    project_name: Optional[str] = None,
    default_dir: Optional[Union[Path, str]] = None,
    base_path: Optional[str] = None,
    projects_dir: Optional[Union[Path, str]] = None,
) -> Tuple[Path, Optional[str]]:
    """Resolves target workspace directory from base path string and project name.

    Returns:
        Tuple[Path, Optional[str]]: A tuple containing the resolved target Path
        and an optional error message (None on success).
    """
    effective_base_path = base_path_str or base_path
    effective_default_dir = default_dir or projects_dir

    if effective_base_path:
        target_path = Path(str(effective_base_path)).expanduser().resolve()
        if project_name and (target_path / str(project_name)).is_dir():
            target_path = target_path / str(project_name)
    elif project_name:
        if effective_default_dir:
            target_path = (Path(effective_default_dir) / str(project_name)).resolve()
        else:
            target_path = resolve_project_path(project_name)
    elif effective_default_dir:
        target_path = Path(effective_default_dir).resolve()
    else:
        target_path = Path.cwd().resolve()

    return target_path, None