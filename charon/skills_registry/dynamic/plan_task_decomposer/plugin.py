"""
Skill: Plan Task Decomposer
Description: Handles DAG task decomposition and multi-step engineering build sequencing.
"""

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union

import ollama

logger = logging.getLogger("charon.skills.plan_task_decomposer")

DAG_SYSTEM_PROMPT = (
    "You are The Planner, the chief orchestrator for Charon.\n"
    "Decompose the user's request into a sequential JSON plan of agent executions.\n\n"
    "AVAILABLE AGENTS & ACTIONS:\n"
    "- The_Archivist: 'search_ledger' (params: query), 'search_datasheets' (params: query), 'store_record' (params: fact, category)\n"
    "- The_Cleaner: 'list_projects', 'initialize_project_workspace', 'commit_workspace', 'sweep_cad_iterations' (params: base_path, project_name)\n"
    "- The_Planner: 'execute_sandbox_code', 'analyze_error_logs', 'draft_build_sequence' (params: prompt, log_content, objective)\n"
    "- The_Engineer: 'solve_coding_task', 'generate_script' (params: problem, prompt)\n"
    "- The_Generalist: 'answer_query', 'synthesize', 'execute_system_command' (params: prompt, context, command)\n"
    "- The_Overseer: 'get_system_health', 'optimize_databases', 'prune_logs_and_cache'\n"
    "- The_Steward: 'control_appliance', 'read_sensor_net' (params: target_device, command)\n"
    "- The_Quartermaster: 'fetch_datasheet', 'check_inventory' (params: query)\n"
    "- The_Scout: 'web_search' (params: query)\n"
    "- The_Machinist: 'convert_cad', 'generate_gcode' (params: file_path)\n"
    "- The_Spark: 'flash_firmware', 'compile_microcontroller' (params: project_path)\n\n"
    "OUTPUT FORMAT: Strictly return a JSON list of objects matching this schema:\n"
    "[\n"
    '  {"step": 1, "agent": "The_Archivist", "action": "search_ledger", "parameters": {"query": "..."}},\n'
    '  {"step": 2, "agent": "The_Cleaner", "action": "list_projects", "parameters": {"base_path": "$STEP_1_OUTPUT"}}\n'
    "]\n"
    "Do not include commentary or markdown wrapping outside the JSON."
)

BUILD_SEQUENCE_SYSTEM_PROMPT = (
    "You are The Planner, a Metacognitive Supervisor and Chief Mechatronics Architect.\n"
    "Your task is to draft a clean, precise, and structured engineering specification and build plan.\n\n"
    "FORMAT & STRUCTURE RULES:\n"
    "1. OBJECTIVE SUMMARY: Briefly restate the target system/feature.\n"
    "2. ARCHITECTURE & COMPONENT BREAKDOWN: List required files, scripts, modules, hardware, or API dependencies.\n"
    "3. STEP-BY-STEP EXECUTION SEQUENCE: Numbered order of execution for engineering/code implementation.\n"
    "4. FILE STRUCTURE & TARGET PATHS: Explicitly state required file paths and directories.\n"
    "5. VERIFICATION & EDGE CASES: Define tests or criteria needed to confirm build success.\n\n"
    "Do not output generic chatter. Focus strictly on providing an actionable blueprint that an engineer can execute directly."
)


def _extract_param_dict(payload: Optional[Union[Dict[str, Any], Any]]) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload.get("params", payload)
    elif payload and hasattr(payload, "params"):
        return payload.params or {}
    return {}


def resolve_objective(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> str:
    """Multi-tier fallback extraction for goal/objective strings."""
    p_dict = _extract_param_dict(payload)

    obj = (
        params.get("objective")
        or params.get("task")
        or params.get("goal")
        or p_dict.get("objective")
        or p_dict.get("task")
        or p_dict.get("goal")
        or getattr(payload, "objective", None)
        or getattr(payload, "task", None)
    )
    if obj:
        return str(obj).strip()

    return raw_prompt.strip() if raw_prompt else ""


async def decompose_task(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> Dict[str, Any]:
    """Decomposes a task into a structured agent DAG execution sequence."""
    objective = resolve_objective(params, raw_prompt=raw_prompt, payload=payload)
    if not objective:
        return {"status": "error", "error": "No objective provided for task decomposition.", "result": []}

    logger.info(f"[TaskDecomposer] Decomposing objective into DAG: {objective}")

    try:
        response = await client.generate(
            model=model_name,
            system=DAG_SYSTEM_PROMPT,
            prompt=f"Objective: {objective}",
            format="json",
        )
        raw_response = response.get("response", "[]").strip()

        if "```" in raw_response:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_response, re.DOTALL)
            if match:
                raw_response = match.group(1).strip()

        plan = json.loads(raw_response)
        parsed_plan = plan if isinstance(plan, list) else []
        return {"status": "success", "result": parsed_plan}

    except Exception as e:
        logger.error(f"[TaskDecomposer] Parsing failure during DAG generation: {e}")
        return {"status": "error", "error": str(e), "result": []}


async def draft_build_sequence(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> Dict[str, Any]:
    """Drafts an engineering blueprint with optional real-time streaming."""
    objective = resolve_objective(params, raw_prompt=raw_prompt, payload=payload)
    cb = stream_callback or params.get("stream_callback")

    if not objective:
        return {"status": "error", "error": "An 'objective' parameter is required to draft a sequence."}

    logger.info(f"[BuildSequencer] Drafting blueprint for: {objective}")

    try:
        plan_response = ""
        if cb:
            async for chunk in await client.generate(
                model=model_name,
                system=BUILD_SEQUENCE_SYSTEM_PROMPT,
                prompt=f"Objective: {objective}",
                stream=True,
            ):
                token = chunk.get("response", "")
                plan_response += token
                cb(token)
        else:
            response = await client.generate(
                model=model_name,
                system=BUILD_SEQUENCE_SYSTEM_PROMPT,
                prompt=f"Objective: {objective}",
            )
            plan_response = response.get("response", "").strip()

        return {"status": "success", "result": plan_response.strip()}

    except Exception as e:
        logger.error(f"[BuildSequencer] Inference failure during sequencing: {e}")
        return {"status": "error", "error": f"Unable to draft build sequence: {str(e)}"}