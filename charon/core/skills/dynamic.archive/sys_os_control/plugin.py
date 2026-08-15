"""
Plugin entrypoint module for sys_os_control.
"""

import os
import subprocess
from typing import Any, Dict

from charon.config.paths import PROJECTS_DIR, resolve_project_path


def handle_execute_system_command(params: Dict[str, Any]) -> Dict[str, Any]:
    command = params.get("command") or params.get("cmd")
    if not command:
        return {"status": "error", "message": "Parameter 'command' is required."}

    cwd_raw = params.get("cwd") or params.get("target_dir")
    cwd = str(resolve_project_path(cwd_raw)) if cwd_raw else str(PROJECTS_DIR)
    timeout = float(params.get("timeout", 30.0))

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "status": "success" if result.returncode == 0 else "failure",
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def handle_launch_gui_viewer(params: Dict[str, Any]) -> Dict[str, Any]:
    file_path_raw = params.get("file_path") or params.get("target")
    if not file_path_raw:
        return {
            "status": "error",
            "message": "Parameter 'file_path' is required.",
        }

    resolved = resolve_project_path(file_path_raw)
    if not resolved.exists():
        return {
            "status": "error",
            "message": f"Target path does not exist: {resolved}",
        }

    try:
        subprocess.Popen(
            ["xdg-open", str(resolved)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "success",
            "message": f"Launched GUI viewer for {resolved.name}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to open GUI viewer: {e}"}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "execute_system_command":
        return handle_execute_system_command(params)
    elif action_name == "launch_gui_viewer":
        return handle_launch_gui_viewer(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'sys_os_control'."
    )