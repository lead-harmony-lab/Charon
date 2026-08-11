"""
Skill: Plan Task Decomposer
Description: Handles DAG task decomposition and multi-step engineering build sequencing dynamically bound to SkillLibrarian SSOT.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

import ollama

logger = logging.getLogger("charon.skills.plan_task_decomposer")

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


def _get_active_agent_capabilities(librarian: Optional[Any] = None) -> str:
    """Queries SkillLibrarian SSOT to format available agents and their high-level role descriptions."""
    try:
        if librarian is None:
            from charon.core.skills.librarian import SkillLibrarian
            librarian = SkillLibrarian.get_instance()

        # 1. Prefer rich agent manifest from librarian if available
        if hasattr(librarian, "get_active_agent_manifest"):
            manifest = librarian.get_active_agent_manifest()
            lines = []
            for entry in manifest:
                lines.append(
                    f"- AGENT ID: '{entry['agent_id']}'\n"
                    f"  ROLE/PURPOSE: {entry.get('description', 'General task execution agent.')}"
                )
            if lines:
                return "\n\n".join(lines)

        # 2. Fall back to aggregating active agent roles
        elif hasattr(librarian, "get_all_active_skills"):
            skills = librarian.get_all_active_skills()
            agent_map = {}
            for s in skills:
                agent = s.get("primary_role_id") or s.get("agent_id") or "system_generalist"
                desc = s.get("description", "")
                if agent not in agent_map:
                    agent_map[agent] = set()
                if desc:
                    agent_map[agent].add(desc)

            lines = []
            for agent_id, descs in agent_map.items():
                desc_str = " | ".join(descs) or "General task execution agent."
                lines.append(
                    f"- AGENT ID: '{agent_id}'\n"
                    f"  ROLE/PURPOSE: {desc_str}"
                )
            if lines:
                return "\n\n".join(lines)

    except Exception as e:
        logger.warning(f"[TaskDecomposer] Dynamic agent lookup failed, using fallback: {e}")

    # Fallback to known system roles without hardcoding specific action methods
    return (
        "- AGENT ID: 'system_generalist'\n"
        "  ROLE/PURPOSE: General query processing, task synthesis, and fallback execution.\n\n"
        "- AGENT ID: 'system_planner'\n"
        "  ROLE/PURPOSE: DAG sequence decomposition and workflow planning."
    )


def _build_dag_system_prompt(librarian: Optional[Any] = None) -> str:
    """Constructs the DAG System Prompt enforcing high-level agent routing rather than skill micromanagement."""
    capabilities_block = _get_active_agent_capabilities(librarian)

    return (
        "You are the Chief System Planner in a multi-agent architecture.\n"
        "Your role is STRICTLY HIGH-LEVEL ORCHESTRATION. You draft Directed Acyclic Graphs (DAGs) "
        "that assign clear objectives to specialized agents in your swarm.\n\n"
        "REQUIRED AGENT SELECTION PROCESS:\n"
        "1. IDENTIFY WORK REQUIREMENTS: Determine what general capability or domain expertise is needed for a step.\n"
        "2. CROSS-REFERENCE MANIFEST: Compare the requirement against the ROLE/PURPOSE descriptions in the manifest below.\n"
        "3. MAP TO EXACT AGENT ID: Assign the step to the verbatim AGENT ID bound to that purpose.\n"
        "4. STRICT NON-HALLUCINATION: Do NOT invent role or agent names (e.g., 'coder', 'system_coder', 'developer'). "
        "You MUST strictly assign one of the AGENT IDs explicitly listed in the manifest below.\n\n"
        "AVAILABLE AGENTS & ROLES:\n"
        f"{capabilities_block}\n\n"
        "RULES & CONSTRAINTS:\n"
        "1. AGENT SELECTION: The 'agent' string in each step MUST match an active AGENT ID verbatim.\n"
        "2. INVERSION OF CONTROL: Do NOT specify action or skill function names. Define high-level goals in the 'objective' field. The assigned agent will dynamically select its own database tools to fulfill the objective.\n"
        "3. OUTPUT FORMAT: Return ONLY a valid JSON object containing a single root key called 'steps' (an array of objects).\n"
        "4. SCHEMA: Each object requires: 'step' (int), 'agent' (string ID), 'objective' (string), 'parameters' (dict), and 'depends_on' (array of ints).\n"
        "5. STATE TRANSFER: Use '$STEP_X_OUTPUT' in 'parameters' to pass context or data from step X to downstream steps.\n"
        "6. VARIABLE BOUNDARIES: The '$STEP_X_OUTPUT' syntax is ONLY allowed inside the 'parameters' dictionary. "
        "The 'agent' field MUST be a static string literal from the manifest and CANNOT contain '$STEP_' references."
    )


async def decompose_task(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[Dict[str, Any], Any]] = None,
    librarian: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Decomposes a task into a structured agent DAG execution sequence dynamically."""
    objective = resolve_objective(params, raw_prompt=raw_prompt, payload=payload)
    if not objective:
        return []

    system_prompt = _build_dag_system_prompt(librarian)
    logger.info(f"[TaskDecomposer] Decomposing objective into DAG: {objective}")

    try:
        response = await client.generate(
            model=model_name,
            system=system_prompt,
            prompt=f"Objective: {objective}",
            format="json",
        )
        raw_response = response.get("response", "{}").strip()

        if "```" in raw_response:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_response, re.DOTALL)
            if match:
                raw_response = match.group(1).strip()

        plan = json.loads(raw_response)

        # Safely extract the list whether the LLM returns an object or a direct array
        if isinstance(plan, dict):
            parsed_plan = plan.get("steps", plan.get("dag", plan.get("plan", [])))
            if not parsed_plan:
                for val in plan.values():
                    if isinstance(val, list):
                        parsed_plan = val
                        break
        elif isinstance(plan, list):
            parsed_plan = plan
        else:
            parsed_plan = []

        # --- PRE-EXECUTION AGENT SANITIZATION GUARDRAIL ---
        valid_agents = set()
        try:
            lib = librarian
            if lib is None:
                from charon.core.skills.librarian import SkillLibrarian
                lib = SkillLibrarian.get_instance()

            if hasattr(lib, "get_active_capabilities_map"):
                valid_agents = set(lib.get_active_capabilities_map().keys())
            elif hasattr(lib, "get_all_active_skills"):
                skills = lib.get_all_active_skills()
                valid_agents = {
                    s.get("primary_role_id") or s.get("agent_id") or "system_generalist"
                    for s in skills
                }
        except Exception as e:
            logger.warning(f"[TaskDecomposer] Could not retrieve active agents for plan validation: {e}")

        if not valid_agents:
            valid_agents = {"system_generalist", "system_planner"}

        default_fallback_agent = "system_generalist" if "system_generalist" in valid_agents else next(iter(valid_agents))
        last_valid_agent = default_fallback_agent

        sanitized_plan = []
        for step in parsed_plan:
            if not isinstance(step, dict):
                continue

            agent_ref = str(step.get("agent", "")).strip()

            # Fix variable placeholders ($STEP_X_OUTPUT) or non-existent agents in the structural 'agent' key
            if "$STEP_" in agent_ref or agent_ref not in valid_agents:
                logger.warning(
                    f"[TaskDecomposer] Invalid or variable agent reference '{agent_ref}' in step {step.get('step')}. "
                    f"Sanitizing step agent to fallback '{last_valid_agent}'."
                )
                step["agent"] = last_valid_agent
            else:
                last_valid_agent = agent_ref

            sanitized_plan.append(step)

        logger.info(f"[TaskDecomposer] Successfully parsed and sanitized {len(sanitized_plan)} execution steps.")
        return sanitized_plan

    except Exception as e:
        logger.error(f"[TaskDecomposer] Parsing failure during DAG generation: {e}")
        return []


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


# =====================================================================
# --- CHARON SYSTEM EXECUTION BRIDGES ---
# =====================================================================

async def handle_decompose_task_async(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Asynchronous wrapper for decompose_task execution."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("prompt") or params.get("raw_prompt") or params.get("query") or ""

    return await decompose_task(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
        payload=params.get("payload")
    )


def handle_decompose_task(params: Dict[str, Any]) -> Union[List[Dict[str, Any]], Coroutine]:
    """Entrypoint matching DB handler_name column for 'decompose_task'."""
    try:
        loop = asyncio.get_running_loop()
        return handle_decompose_task_async(params)
    except RuntimeError:
        return asyncio.run(handle_decompose_task_async(params))


async def handle_draft_build_sequence_async(params: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous wrapper for draft_build_sequence execution."""
    client = ollama.AsyncClient()
    model_name = params.get("model_name", "llama3.1")
    raw_prompt = params.get("prompt") or params.get("raw_prompt") or params.get("query") or ""

    return await draft_build_sequence(
        client=client,
        model_name=model_name,
        params=params,
        raw_prompt=raw_prompt,
        payload=params.get("payload")
    )


def handle_draft_build_sequence(params: Dict[str, Any]) -> Union[Dict[str, Any], Coroutine]:
    """Entrypoint matching DB handler_name column for 'draft_build_sequence'."""
    try:
        loop = asyncio.get_running_loop()
        return handle_draft_build_sequence_async(params)
    except RuntimeError:
        return asyncio.run(handle_draft_build_sequence_async(params))


def execute_action(action_name: str, params: Dict[str, Any]) -> Union[Dict[str, Any], List[Dict[str, Any]], Coroutine]:
    """Main dispatch router invoked by Charon system agents."""
    if action_name == "decompose_task":
        return handle_decompose_task(params)
    elif action_name == "draft_build_sequence":
        return handle_draft_build_sequence(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'plan_task_decomposer'."
    )