"""
Plugin entrypoint module for code_python_interpreter.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess


async def handle_execute_sandbox_code(params: Dict[str, Any]) -> Dict[str, Any]:
    code = params.get("code") or params.get("script_contents")
    if not code:
        return {"status": "error", "message": "No 'code' parameter provided."}

    target_dir_raw = params.get("target_dir") or params.get("cwd")
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )
    timeout = float(params.get("timeout", 30.0))
    python_cmd = params.get("python_cmd", "python3")

    output, is_success = await run_script_in_subprocess(
        code, cwd=target_dir, python_cmd=python_cmd, timeout=timeout
    )
    audit_ok, audit_msg = (
        audit_written_artifacts(code, cwd=target_dir)
        if is_success
        else (False, "Skipped due to execution failure.")
    )

    return {
        "status": "success" if (is_success and audit_ok) else "failure",
        "output": output,
        "artifact_audit": audit_msg,
    }


async def handle_run_existing_script(params: Dict[str, Any]) -> Dict[str, Any]:
    script_path_raw = params.get("script_path") or params.get("file_path")
    if not script_path_raw:
        return {
            "status": "error",
            "message": "Parameter 'script_path' is required.",
        }

    resolved_path = resolve_project_path(script_path_raw)
    if not resolved_path.exists():
        return {
            "status": "error",
            "message": f"Script not found at: {resolved_path}",
        }

    code = resolved_path.read_text(encoding="utf-8")
    target_dir = str(resolved_path.parent)
    timeout = float(params.get("timeout", 30.0))
    python_cmd = params.get("python_cmd", "python3")

    output, is_success = await run_script_in_subprocess(
        code, cwd=target_dir, python_cmd=python_cmd, timeout=timeout
    )
    return {
        "status": "success" if is_success else "failure",
        "output": output,
        "script": str(resolved_path),
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "execute_sandbox_code":
        return asyncio.run(handle_execute_sandbox_code(params))
    elif action_name == "run_existing_script":
        return asyncio.run(handle_run_existing_script(params))

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'code_python_interpreter'."
    )