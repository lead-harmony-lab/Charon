"""
Plugin entrypoint module for code_self_healing_solver.
Standardized for direct async execution without asyncio.run event loop hijacks.
"""

import logging
import re
from typing import Any, Dict
import ollama

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess

logger = logging.getLogger("CHAROND.Skills.SelfHealingSolver")


async def handle_solve_edge_case(params: Dict[str, Any]) -> Dict[str, Any]:
    problem = params.get("problem") or params.get("prompt") or params.get("task")
    if not problem or not str(problem).strip():
        raise ValueError("[SELF_HEALING_SOLVER] Parameter 'problem' or 'prompt' is required.")

    # Strict bounds when invoked via runtime engine
    max_attempts = min(int(params.get("max_attempts", 1)), 2)  # Cap at max 2 attempts
    timeout = float(params.get("timeout", 15.0))              # 15s execution timeout

    target_dir_raw = params.get("target_dir") or params.get("base_path")
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )
    model_name = params.get("model_name", "qwen2.5-coder:latest")
    python_cmd = params.get("python_cmd", "python3")

    client = ollama.AsyncClient()
    system_prompt = (
        "You are an expert Python Software Engineer specializing in dynamic script resolution.\n"
        "RULES:\n"
        "1. Output ONLY runnable Python code wrapped in a ```python ``` markdown code block.\n"
        "2. Handle exceptions gracefully and print explicit diagnostic output to stdout.\n"
        "3. NEVER use interactive functions like input().\n"
    )

    feedback = ""
    last_code = ""

    for attempt in range(1, max_attempts + 1):
        prompt_text = (
            f"Task: {problem}\nTarget Workspace: {target_dir}"
            if attempt == 1
            else f"Task: {problem}\nFeedback from attempt {attempt-1}:\n{feedback}\nFix and return corrected code."
        )

        response = await client.generate(
            model=model_name, system=system_prompt, prompt=prompt_text
        )
        raw_response = response.get("response", "").strip()
        code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL)
        code = code_match.group(1).strip() if code_match else raw_response.strip()

        if not code:
            feedback = "Inference engine returned empty script block."
            continue

        last_code = code
        output, is_success = await run_script_in_subprocess(
            code, cwd=target_dir, python_cmd=python_cmd, timeout=timeout
        )

        if is_success:
            audit_ok, audit_msg = audit_written_artifacts(code, cwd=target_dir)
            if not audit_ok:
                feedback = f"{output}\n\n{audit_msg}"
                continue

            return {
                "status": "success",
                "attempts": attempt,
                "output": output,
                "verification": audit_msg,
                "final_code": code,
            }

        feedback = output

    # HARD FAIL: Raise exception so Dispatcher/Router halts instead of retrying silently
    raise RuntimeError(
        f"[SOLVER FAULT] Self-healing code execution failed after {max_attempts} attempts. "
        f"Last error output:\n{feedback}"
    )


# Native Async Entrypoint (Replaces synchronous execute_action wrapper)
async def execute_action_async(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "solve_edge_case":
        return await handle_solve_edge_case(params)
    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'code_self_healing_solver'."
    )