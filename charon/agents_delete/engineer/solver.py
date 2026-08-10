"""
charon/agents/engineer/solver.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Domain handler for self-healing code generation and retry loop.
"""

import logging
import re
from typing import Any, Callable, Dict, Optional, Union
import ollama

from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.intent import DynamicActionPayload
from charon.tools.code import audit_written_artifacts, run_script_in_subprocess

logger = logging.getLogger("CHAROND.Engineer.Solver")


async def handle_solve_edge_case(
    client: ollama.AsyncClient,
    model_name: str,
    python_cmd: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Generates, runs, and self-heals Python code in a loop until the edge case is resolved."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )

    problem = (
        payload_params.get("problem")
        or payload_params.get("prompt")
        or payload_params.get("task")
        or payload_params.get("objective")
        or params.get("problem")
        or params.get("prompt")
        or params.get("task")
        or params.get("objective")
        or getattr(payload, "problem", None)
        or getattr(payload, "prompt", None)
        or raw_prompt
    )
    if not problem or not str(problem).strip():
        return "Error: A 'problem' or 'prompt' parameter is required for code resolution."

    raw_attempts = (
        payload_params.get("max_attempts")
        or params.get("max_attempts")
        or getattr(payload, "max_attempts", None)
        or 3
    )
    try:
        max_attempts = int(raw_attempts)
    except (ValueError, TypeError):
        max_attempts = 3

    raw_timeout = (
        payload_params.get("timeout")
        or params.get("timeout")
        or getattr(payload, "timeout", None)
        or 30.0
    )
    try:
        timeout = float(raw_timeout)
    except (ValueError, TypeError):
        timeout = 30.0

    target_dir_raw = (
        payload_params.get("target_dir")
        or payload_params.get("base_path")
        or params.get("target_dir")
        or params.get("base_path")
        or getattr(payload, "target_dir", None)
    )
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )

    logger.info(f"The Engineer tackling edge case: {problem}")

    system_prompt = (
        "You are an expert Python Software Engineer specializing in dynamic script resolution.\n"
        "Your objective: Write self-contained, robust Python code to solve specific operational edge cases.\n\n"
        "RULES:\n"
        "1. Output ONLY runnable Python code wrapped in a ```python ``` markdown code block.\n"
        "2. Include all required standard library or installed imports.\n"
        "3. Handle exceptions gracefully and print explicit diagnostic output to stdout.\n"
        "4. NEVER use interactive functions like input().\n"
        "5. Apply defense-in-depth coding: account for non-existent paths, unusual file encodings, and missing inputs."
    )

    feedback = ""
    last_code = ""

    for attempt in range(1, max_attempts + 1):
        logger.info(f"Self-healing pass {attempt}/{max_attempts}...")

        if attempt == 1:
            prompt_text = f"Task/Edge-Case Objective: {problem}\nTarget Workspace: {target_dir}"
        else:
            prompt_text = (
                f"Task/Edge-Case Objective: {problem}\n"
                f"Target Workspace: {target_dir}\n\n"
                f"CRITICAL: Your previous code failed with the following execution output/traceback:\n"
                f"```\n{feedback}\n```\n\n"
                f"Previous Code Attempt:\n```python\n{last_code}\n```\n\n"
                f"Analyze the runtime failure, fix the underlying bug or edge case handling, "
                f"and return the complete corrected Python script."
            )

        try:
            response = await client.generate(
                model=model_name,
                system=system_prompt,
                prompt=prompt_text,
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
                feedback = "Error: Inference engine returned empty script block."
                continue

            last_code = code

            # Execute in sandbox subshell with process timeout
            output, is_success = await run_script_in_subprocess(
                code,
                cwd=target_dir,
                python_cmd=python_cmd,
                timeout=timeout,
                stream_callback=stream_callback,
            )

            if is_success:
                # AST Disk Artifact Verification
                audit_ok, audit_msg = audit_written_artifacts(
                    code, cwd=target_dir
                )

                if not audit_ok:
                    feedback = f"{output}\n\n{audit_msg}"
                    logger.warning(
                        f"Attempt {attempt} failed AST artifact check: {audit_msg}"
                    )
                    continue

                logger.info(
                    f"Edge case resolved successfully on attempt {attempt}."
                )
                return (
                    f"### Edge Case Resolved (Attempt {attempt}/{max_attempts})\n\n"
                    f"**Execution Output:**\n```\n{output}\n```\n\n"
                    f"**Verification Status:** {audit_msg}\n\n"
                    f"**Final Working Script:**\n```python\n{code}\n```"
                )
            else:
                feedback = output
                logger.warning(
                    f"Attempt {attempt} failed execution with output:\n{output}"
                )

        except Exception as e:
            feedback = f"Inference/Execution failure: {str(e)}"
            logger.error(f"Error during repair attempt {attempt}: {e}")

    return (
        f"### Failed to Resolve Edge Case after {max_attempts} attempts.\n\n"
        f"**Last Error/Traceback:**\n```\n{feedback}\n```\n\n"
        f"**Last Attempted Script:**\n```python\n{last_code}\n```"
    )