"""
charon/agents/engineer/runner.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Domain handler for running existing Python scripts and dynamic sandbox
execution. Updated for DynamicActionPayload intent parsing and sanitized encoding.
"""

import logging
import os
import re
from typing import Any, Callable, Dict, Optional, Union

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.intent import DynamicActionPayload
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess

logger = logging.getLogger("CHAROND.Engineer.Runner")


async def handle_execute_sandbox_code(
    python_cmd: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Executes a dynamic code payload directly in the guarded sandbox with AST verification."""
    params = params or {}
    p_params = (
        getattr(payload, "params", {})
        if isinstance(getattr(payload, "params", None), dict)
        else {}
    )
    extra_code = None

    if payload and hasattr(payload, "model_extra") and payload.model_extra:
        extra_code = payload.model_extra.get("code") or payload.model_extra.get("prompt")
    elif isinstance(payload, dict):
        extra_code = payload.get("code") or payload.get("prompt")

    code = (
        getattr(payload, "code", None)
        or getattr(payload, "prompt", None)
        or getattr(payload, "problem", None)
        or extra_code
        or p_params.get("code")
        or p_params.get("prompt")
        or p_params.get("script")
        or params.get("code")
        or params.get("prompt")
        or params.get("script")
    )
    target_dir_raw = (
        getattr(payload, "target_dir", None)
        or p_params.get("target_dir")
        or p_params.get("base_path")
        or params.get("target_dir")
        or params.get("base_path")
    )
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )
    raw_timeout = (
        getattr(payload, "timeout", None)
        or p_params.get("timeout")
        or params.get("timeout")
        or 30.0
    )
    try:
        timeout = float(raw_timeout)
    except (ValueError, TypeError):
        timeout = 30.0

    if not code:
        return "Error: No code payload provided for sandbox execution."

    # Strip markdown formatting if embedded in code blocks
    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", str(code), re.DOTALL)
    clean_code = (
        code_match.group(1).strip() if code_match else str(code).strip()
    )
    output, success = await run_script_in_subprocess(
        clean_code,
        cwd=target_dir,
        python_cmd=python_cmd,
        timeout=timeout,
        stream_callback=stream_callback,
    )
    audit_ok, audit_msg = audit_written_artifacts(clean_code, cwd=target_dir)
    status_str = "SUCCESS" if (success and audit_ok) else "FAILED"
    return (
        f"### Sandbox Execution Result [{status_str}]\n\n"
        f"**Output:**\n```\n{output}\n```\n\n"
        f"**Disk Artifact Status:** {audit_msg}"
    )


async def handle_run_existing_script(
    python_cmd: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Executes an existing script file on disk."""
    params = params or {}
    p_params = (
        getattr(payload, "params", {})
        if isinstance(getattr(payload, "params", None), dict)
        else {}
    )
    script_path_raw = (
        getattr(payload, "script_path", None)
        or (payload.get("script_path") if isinstance(payload, dict) else None)
        or p_params.get("script_path")
        or p_params.get("path")
        or params.get("script_path")
        or params.get("path")
    )
    if not script_path_raw:
        return "Error: A 'script_path' parameter is required to run an existing script."

    resolved_path = resolve_project_path(str(script_path_raw))
    if not resolved_path.exists():
        return f"Error: Specified script path '{script_path_raw}' does not exist on disk."

    raw_timeout = (
        getattr(payload, "timeout", None)
        or p_params.get("timeout")
        or params.get("timeout")
        or 30.0
    )
    try:
        timeout = float(raw_timeout)
    except (ValueError, TypeError):
        timeout = 30.0

    target_dir_raw = (
        getattr(payload, "target_dir", None)
        or p_params.get("target_dir")
        or params.get("target_dir")
        or os.path.dirname(str(resolved_path))
    )
    target_dir = str(resolve_project_path(target_dir_raw))

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        return f"Error reading script file '{resolved_path}': {e}"

    output, success = await run_script_in_subprocess(
        code,
        cwd=target_dir,
        python_cmd=python_cmd,
        timeout=timeout,
        stream_callback=stream_callback,
    )
    audit_ok, audit_msg = audit_written_artifacts(code, cwd=target_dir)
    status = "Success" if (success and audit_ok) else "Failed"
    return (
        f"### Script Execution ({status})\n\n"
        f"**Output:**\n```\n{output}\n```\n\n"
        f"**Disk Artifact Status:** {audit_msg}"
    )