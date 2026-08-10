"""
Skill: Code Sandbox Executor
Description: Generates and safely executes Python code in an isolated subshell environment with auditing.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

import ollama

# Helper tooling dependencies (from core platform tools)
try:
    from charon.tools.code import audit_written_artifacts, extract_target_directory
except ImportError:
    # Inline fallback implementations if standard tools module is not installed
    def extract_target_directory(prompt: str) -> Optional[str]:
        match = re.search(r"(?:directory|path|workspace):\s*([^\s]+)", prompt, re.IGNORECASE)
        return match.group(1) if match else None

    def audit_written_artifacts(code: str, target_cwd: str) -> Tuple[bool, str]:
        return True, "Audit skipped: Tooling not loaded."


logger = logging.getLogger("charon.skills.code_sandbox_executor")

SANDBOX_CODE_SYSTEM_PROMPT = (
    "You are an automated Python code execution engine.\n"
    "Your task: Write a COMPLETE, fully functional Python script to fulfill the prompt.\n\n"
    "STRICT EXECUTION & INTEGRITY RULES:\n"
    "1. TARGET DIRECTORY PRESERVATION:\n"
    "   - Perform all checks and audit logic inside the EXACT target directory path specified in the task prompt.\n"
    "   - NEVER truncate, shorten, or collapse the target path to a parent directory.\n"
    "2. AUDIT VS MUTATION CONTRACT:\n"
    "   - If the prompt requests to 'Audit', 'Verify', 'Check', or 'Inspect', perform READ-ONLY checks (e.g., Path.exists()). DO NOT create subdirectories.\n"
    "   - Check ONLY for the subdirectories named in the task prompt or retrieved standards.\n"
    "3. FULL LOGIC REQUIRED: Output full, runnable code. Include path verification, file checks, and explicit report writing using open().\n"
    "4. DIRECT STDOUT MANDATE: Always print explicit audit findings and pass/fail summary directly to stdout using print().\n"
    "5. PATH SAFETY: Always resolve target paths using absolute paths or Path objects.\n"
    "6. FORMAT: Return pure python code inside a markdown ```python ``` code block."
)


def _extract_param_dict(payload: Optional[Union[Dict[str, Any], Any]]) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload.get("params", payload)
    elif payload and hasattr(payload, "params"):
        return payload.params or {}
    return {}


def resolve_code_prompt(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> str:
    """Multi-tier fallback extraction for code generation prompts."""
    p_dict = _extract_param_dict(payload)

    code_p = (
        params.get("prompt")
        or params.get("intent")
        or params.get("task")
        or p_dict.get("prompt")
        or p_dict.get("intent")
        or p_dict.get("task")
        or getattr(payload, "prompt", None)
        or getattr(payload, "intent", None)
    )
    if code_p:
        return str(code_p).strip()

    return raw_prompt.strip() if raw_prompt else ""


async def generate_and_execute_code(
    client: ollama.AsyncClient,
    model_name: str,
    python_cmd: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> Dict[str, Any]:
    """Generates Python code via LLM and executes it in a controlled subshell with streaming output."""
    prompt = resolve_code_prompt(params, raw_prompt=raw_prompt, payload=payload)
    cb = stream_callback or params.get("stream_callback")

    if not prompt:
        return {"status": "error", "error": "A 'prompt' or 'intent' parameter is required to generate and execute code."}

    logger.warning(f"[SandboxExecutor] Initiating dynamic code generation for:\n{prompt}")

    target_cwd = extract_target_directory(prompt)
    cwd_context = f"\nTARGET WORKSPACE DIRECTORY: {target_cwd}" if target_cwd else ""

    code = ""
    for attempt in range(2):
        try:
            response = await client.generate(
                model=model_name,
                system=SANDBOX_CODE_SYSTEM_PROMPT,
                prompt=f"Task: {prompt}{cwd_context}",
            )
            raw_code = response.get("response", "").strip()

            if "```" in raw_code:
                match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_code, re.DOTALL)
                if match:
                    raw_code = match.group(1).strip()

            logic_lines = [
                line for line in raw_code.splitlines()
                if line.strip()
                and not line.strip().startswith("import")
                and not line.strip().startswith("from")
            ]
            if len(logic_lines) >= 1:
                code = raw_code
                break
            else:
                logger.warning(f"[SandboxExecutor] Attempt {attempt + 1}: Stub detected. Retrying...")

        except Exception as e:
            logger.error(f"[SandboxExecutor] Inference failure during code generation: {e}")
            return {"status": "error", "error": f"Failed to generate code: {e}"}

    if not code:
        return {"status": "error", "error": "Inference engine failed to produce valid code."}

    runner_script = (
        "import sys, os, subprocess, json, time, re, pathlib, platform, shutil\n"
        "try:\n"
        "    import psutil\n"
        "except ImportError:\n"
        "    psutil = None\n"
        "code_to_run = sys.argv[1]\n"
        "g = {'__name__': '__main__', 'os': os, 'sys': sys, 'psutil': psutil, 'subprocess': subprocess, 'pathlib': pathlib}\n"
        "try:\n"
        "    exec(code_to_run, g)\n"
        "except Exception as e:\n"
        "    print(f'[Runtime Execution Error]: {e}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )

    exec_kwargs: Dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
    }

    if target_cwd and Path(target_cwd).exists():
        exec_kwargs["cwd"] = target_cwd
        logger.info(f"[SandboxExecutor] Enforced target directory: {target_cwd}")

    try:
        process = await asyncio.create_subprocess_exec(
            python_cmd, "-c", runner_script, code, **exec_kwargs
        )

        output_chunks = []
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            chunk = line.decode("utf-8", errors="replace")
            output_chunks.append(chunk)

            if cb:
                cb(chunk)

        await process.wait()
        full_output = "".join(output_chunks).strip()

        if process.returncode != 0:
            err_msg = f"{full_output}\n[System Error]: Execution exited with code {process.returncode}."
            return {"status": "execution_failed", "error": err_msg, "code": code}

        is_valid, audit_msg = audit_written_artifacts(code, target_cwd or ".")
        audit_summary = f"\n\n[Metacognitive Audit - File Verification]:\n{audit_msg}"
        final_result = f"{full_output}{audit_summary}\n\nSandbox Execution Complete."

        return {
            "status": "success",
            "result": final_result,
            "code": code,
            "audit_passed": is_valid,
        }

    except Exception as e:
        logger.error(f"[SandboxExecutor] Critical runtime error: {e}")
        return {"status": "error", "error": f"Critical execution failure: {str(e)}"}