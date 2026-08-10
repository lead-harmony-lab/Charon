"""
Plugin entrypoint module for code_self_healing_solver.
"""

import asyncio
import logging
import re
from typing import Any, Dict, Optional
import ollama

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess

logger = logging.getLogger("CHAROND.Skills.SelfHealingSolver")


async def handle_solve_edge_case(params: Dict[str, Any]) -> Dict[str, Any]:
    problem = params.get("problem") or params.get("prompt") or params.get("task")
    if not problem or not str(problem).strip():
        return {
            "status": "error",
            "message": "A 'problem' or 'prompt' parameter is required.",
        }

    max_attempts = int(params.get("max_attempts", 3))
    timeout = float(params.get("timeout", 30.0))
    target_dir_raw = params.get("target_dir") or params.get("base_path")
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )
    model_name = params.get("model_name", "qwen2.5-coder:14b")
    python_cmd = params.get("python_cmd", "python3")

    client = ollama.AsyncClient()
    system_prompt = (
        "You are an expert Python Software Engineer specializing in dynamic script resolution.\n"
        "RULES:\n"
        "1. Output ONLY runnable, completely self-contained Python code wrapped in a ```python ``` markdown code block.\n"
        "2. ALWAYS include all necessary import statements (e.g., import os, sys, datetime, math) at the top of the code.\n"
        "3. Do NOT include introductory conversational prose, explanation, or text outside the code block.\n"
        "4. Handle exceptions gracefully inside the script and print explicit diagnostic output to stdout.\n"
        "5. NEVER use interactive functions like input().\n"
    )

    feedback = ""
    last_code = ""

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            prompt_text = f"Task: {problem}\nTarget Workspace: {target_dir}"
        else:
            prompt_text = (
                f"Task: {problem}\nTarget Workspace: {target_dir}\n\n"
                f"CRITICAL: Previous attempt failed with output:\n```\n{feedback}\n```\n\n"
                f"Previous Code:\n```python\n{last_code}\n```\n\n"
                f"Fix the bug and return the complete corrected Python script including all necessary imports."
            )

        try:
            response = await client.generate(
                model=model_name, system=system_prompt, prompt=prompt_text
            )
            raw_response = response.get("response", "").strip()
            code_match = re.search(
                r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL
            )
            code = (
                code_match.group(1).strip()
                if code_match
                else raw_response.strip()
            )

            if not code:
                feedback = "Inference engine returned empty script block."
                continue

            last_code = code
            output, is_success = await run_script_in_subprocess(
                code, cwd=target_dir, python_cmd=python_cmd, timeout=timeout
            )

            if is_success:
                audit_ok, audit_msg = audit_written_artifacts(
                    code, cwd=target_dir
                )
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
            else:
                feedback = output

        except Exception as e:
            feedback = f"Execution error during attempt {attempt}: {str(e)}"

    # Raise explicit RuntimeError on terminal failure so Dispatcher catches it
    raise RuntimeError(
        f"Self-healing solver failed after {max_attempts} attempt(s).\n"
        f"Last Execution Output/Error:\n{feedback}\n\n"
        f"Last Attempted Code:\n{last_code}"
    )


async def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "solve_edge_case":
        return await handle_solve_edge_case(params)
    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'code_self_healing_solver'."
    )