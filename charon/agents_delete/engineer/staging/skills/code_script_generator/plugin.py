"""
Plugin entrypoint module for code_script_generator.
"""

import asyncio
import re
from typing import Any, Dict
import ollama

from charon.config.paths import PROJECTS_DIR, resolve_project_path


async def handle_generate_script(params: Dict[str, Any]) -> Dict[str, Any]:
    prompt_text = (
        params.get("prompt") or params.get("task") or params.get("objective")
    )
    if not prompt_text:
        return {
            "status": "error",
            "message": "Parameter 'prompt' or 'task' is required.",
        }

    target_dir_raw = params.get("target_dir")
    target_dir = (
        str(resolve_project_path(target_dir_raw))
        if target_dir_raw
        else str(PROJECTS_DIR)
    )
    model_name = params.get("model_name", "qwen2.5-coder:latest")

    client = ollama.AsyncClient()
    system_prompt = (
        "You are an expert Python Software Engineer.\n"
        "Draft standalone, clean, production-grade Python code.\n"
        "Output ONLY code wrapped inside ```python ``` blocks."
    )

    full_prompt = f"Objective: {prompt_text}\nTarget Directory: {target_dir}"
    response = await client.generate(
        model=model_name, system=system_prompt, prompt=full_prompt
    )
    raw_response = response.get("response", "").strip()

    code_match = re.search(
        r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL
    )
    code = (
        code_match.group(1).strip() if code_match else raw_response.strip()
    )

    return {
        "status": "success",
        "generated_code": code,
        "model": model_name,
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "generate_script":
        return asyncio.run(handle_generate_script(params))

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'code_script_generator'."
    )