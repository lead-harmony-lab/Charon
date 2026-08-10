"""
charon/agents/planner/sandbox.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Dynamic Python code generation and isolated subshell execution.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

import ollama

from charon.agents.planner.constants import SANDBOX_CODE_SYSTEM_PROMPT
from charon.agents.planner.utils import resolve_code_prompt
from charon.intent import DynamicActionPayload
from charon.tools.code import audit_written_artifacts, extract_target_directory

logger = logging.getLogger("Charon.Planner.Sandbox")


async def execute_sandbox_code(
    client: ollama.AsyncClient,
    model_name: str,
    python_cmd: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
) -> str:
    """Generates Python code via Ollama and executes it in an isolated sandbox with strict validation."""
    prompt = resolve_code_prompt(params, raw_prompt=raw_prompt, payload=payload)
    if not prompt:
        return "Error: A 'prompt' or 'intent' parameter is required to execute sandbox code."

    logger.warning(
        f"Initiating dynamic code generation for prompt:\n{prompt}"
    )

    target_cwd = extract_target_directory(prompt)
    cwd_context = (
        f"\nTARGET WORKSPACE DIRECTORY: {target_cwd}" if target_cwd else ""
    )

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
                match = re.search(
                    r"```(?:python)?\s*(.*?)\s*```", raw_code, re.DOTALL
                )
                if match:
                    raw_code = match.group(1).strip()

            logic_lines = [
                line
                for line in raw_code.splitlines()
                if line.strip()
                and not line.strip().startswith("import")
                and not line.strip().startswith("from")
            ]
            if len(logic_lines) >= 1:
                code = raw_code
                break
            else:
                logger.warning(
                    f"Attempt {attempt + 1}: Generated code was incomplete or a stub. Retrying..."
                )

        except Exception as e:
            logger.error(f"Inference failure during code generation: {e}")
            return f"Failed to generate code via inference engine: {e}"

    if not code:
        return "Error: The inference engine failed to produce valid executable code."

    logger.info(f"Executing sandbox code snippet:\n{code}")

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
        logger.info(f"Enforced sandbox working directory: {target_cwd}")

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

            if stream_callback:
                stream_callback(chunk)

        await process.wait()
        full_output = "".join(output_chunks).strip()

        if process.returncode != 0:
            return f"{full_output}\n[System Error]: Execution exited with code {process.returncode}."

        is_valid, audit_msg = audit_written_artifacts(code, target_cwd or ".")
        audit_summary = f"\n\n[Metacognitive Audit - File Verification]:\n{audit_msg}"

        return f"{full_output}{audit_summary}\n\nSandbox Execution Complete."

    except Exception as e:
        logger.error(f"Critical failure during dynamic execution: {str(e)}")
        return f"A critical failure occurred during dynamic code execution:\n{str(e)}"