"""
charon/core/skills/storage/staged/core.system.code_runner/plugin.py
System Version: v0.2.1 | File Revision: 3.0.0

Peripheral tool handler providing sandboxed Python execution and artifact auditing.
Optimized for strict CBAC skill_id routing via manifest.json.
"""

import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Dict

logger = logging.getLogger("Charon.Skills.CodeRunner")


def run_script_in_subprocess(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes Python script string inside a temporary file within target workspace directory.
    """
    code = parameters.get("code", "")
    cwd = parameters.get("cwd", ".")
    python_cmd = parameters.get("python_cmd", "python3")
    timeout = float(parameters.get("timeout", 15.0))

    if not code.strip():
        return {
            "is_success": False,
            "output": "Execution error: Empty code payload supplied.",
        }

    os.makedirs(cwd, exist_ok=True)
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", dir=cwd, delete=False) as tmp_file:
            tmp_file.write(code)
            tmp_path = tmp_file.name

        proc = subprocess.run(
            [python_cmd, tmp_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        combined_output = f"{stdout}\n{stderr}".strip() if stderr else stdout

        return {
            "is_success": (proc.returncode == 0),
            "return_code": proc.returncode,
            "output": combined_output or "Script executed successfully with no stdout/stderr output.",
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"[CodeRunner] Script execution timed out after {timeout} seconds.")
        return {
            "is_success": False,
            "return_code": -1,
            "output": f"Script execution timed out after {timeout} seconds.",
        }
    except Exception as e:
        logger.error(f"[CodeRunner] Subprocess execution failed: {e}")
        return {
            "is_success": False,
            "return_code": -1,
            "output": f"Subprocess execution failed with system error: {str(e)}",
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def HT_audit_written_artifacts(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspects written code for high-risk operations and validates workspace state.
    """
    code = parameters.get("code", "")
    cwd = parameters.get("cwd", ".")

    forbidden_patterns = [
        r"shutil\.rmtree\(\s*['\"]/['\"]\s*,",
        r"os\.system\(\s*['\"]rm\s+-rf",
        r"subprocess\.run\(\s*\[?\s*['\"]rm['\"]\s*,\s*['\"]-rf['\"]",
        r"subprocess\.run\(\s*['\"]rm\s+-rf",
    ]

    for pattern in forbidden_patterns:
        if re.search(pattern, code):
            return {
                "audit_ok": False,
                "audit_msg": f"Audit Security Violation: Detected prohibited destructive call matching pattern '{pattern}'.",
            }

    if not os.path.exists(cwd):
        return {
            "audit_ok": False,
            "audit_msg": f"Audit Error: Target workspace path '{cwd}' does not exist.",
        }

    return {
        "audit_ok": True,
        "audit_msg": "Workspace audit passed safely. Zero hazard patterns detected.",
    }


def execute_action(
    skill_id: str,
    parameters: Dict[str, Any],
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Optimal dispatch router strictly aligned with CBAC manifest skill_ids.
    """
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        logger.error(f"[CodeRunner] Failed to load manifest.json: {e}")
        raise ValueError(f"Skill '{skill_id}' could not be routed because manifest.json is missing or invalid.")

    handler_name = None
    for action in manifest.get("actions", []):
        if skill_id == action.get("skill_id"):
            handler_name = action.get("handler_name")
            break

    if not handler_name:
        raise ValueError(
            f"Skill ID '{skill_id}' is not registered in the manifest for package '{manifest.get('package', 'unknown')}'."
        )

    if handler_name not in globals():
        raise NotImplementedError(
            f"Handler function '{handler_name}' is declared in manifest.json but missing in plugin.py."
        )

    handler_func = globals()[handler_name]
    return handler_func(parameters)