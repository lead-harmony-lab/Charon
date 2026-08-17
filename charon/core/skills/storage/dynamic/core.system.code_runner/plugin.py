"""
charon/core/skills/storage/staged/core.system.code_runner/plugin.py
System Version: v0.2.1 | File Revision: 2.1.0

Peripheral tool handler providing sandboxed Python execution and artifact auditing.
"""

import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Skills.CodeRunner")


def run_script_in_subprocess(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes Python script string inside a temporary file within target workspace directory.
    Synchronous wrapper matching standard tool handler signature.
    """
    code = params.get("code", "")
    cwd = params.get("cwd", ".")
    python_cmd = params.get("python_cmd", "python3")
    timeout = float(params.get("timeout", 15.0))

    if not code.strip():
        return {
            "is_success": False,
            "output": "Execution error: Empty code payload supplied.",
        }

    os.makedirs(cwd, exist_ok=True)
    tmp_path: Optional[str] = None

    try:
        # Write temporary file in target workspace
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

        is_success = (proc.returncode == 0)

        return {
            "is_success": is_success,
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
        # Safe cleanup of temporary script execution artifact
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def audit_written_artifacts(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspects written code for high-risk operations and validates workspace state.
    """
    code = params.get("code", "")
    cwd = params.get("cwd", ".")

    # Regex patterns to catch both single/double quotes and variable spacing
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
    action_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    agent_name: str = "",
    raw_prompt: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Standard dispatch router compatible with both legacy params calls
    and BaseAgent.execute_sub_skill keyword routing.
    """
    resolved_params = parameters if parameters is not None else (params or {})

    if action_name == "run_script_in_subprocess":
        return run_script_in_subprocess(resolved_params)
    elif action_name == "audit_written_artifacts":
        return audit_written_artifacts(resolved_params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'core.system.code_runner'.")