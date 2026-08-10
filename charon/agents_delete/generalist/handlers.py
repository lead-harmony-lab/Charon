"""
charon/agents/generalist/handlers.py
System Version: v0.1.0 | File Revision: 1.2.2

Module: Action Handlers for The Generalist Agent.
"""

import logging
import re
from typing import Any, Callable, Dict, Optional, Union

import ollama

from charon.agents.generalist.prompts import (
    CONTINENTAL_GENERALIST_PROMPT,
    KNOWN_CLI_EXECUTABLES,
    PLANNER_HANDOFF_PATTERNS,
    RAG_SYNTHESIS_PROMPT,
)
from charon.core.skills.librarian import SkillLibrarian
from charon.exceptions import HandoffException
from charon.intent.payloads.dynamic import DynamicActionPayload
from charon.tools.math import safe_eval_math
from charon.tools.system import execute_shell_command, get_system_info

# ---> NEW IMPORTS FOR FORCED TELEMETRY OVERRIDE <---
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("CHAROND.Generalist.Handlers")


async def handle_answer_query(
    client: ollama.AsyncClient,
    model_name: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Processes standard conversational or informational queries with forced streaming."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    prompt = (
        payload_params.get("prompt")
        or payload_params.get("query")
        or payload_params.get("command")
        or payload_params.get("text")
        or payload_params.get("question")
        or payload_params.get("problem")
        or getattr(payload, "prompt", None)
        or getattr(payload, "query", None)
        or params.get("prompt")
        or params.get("query")
        or params.get("command")
        or params.get("text")
        or params.get("question")
        or params.get("problem")
        or raw_prompt
    )
    if not prompt or not str(prompt).strip():
        return "Error: A 'prompt' or 'query' parameter is required."

    system_prompt = (
        payload_params.get("system_prompt")
        or params.get("system_prompt")
        or CONTINENTAL_GENERALIST_PROMPT
    )

    logger.info("The Generalist is querying the local inference engine...")

    try:
        full_response = ""
        # ---> FIX: ALWAYS STREAM, bypassing the dropped callback <---
        async for chunk in await client.generate(
            model=model_name,
            prompt=str(prompt),
            system=system_prompt,
            stream=True,
        ):
            token = chunk.get("response", "")
            full_response += token

            if stream_callback:
                stream_callback(token)
            else:
                # Fallback: Push directly to the telemetry bus if UI callback was dropped
                event = TraceEvent(
                    agent_name="The_Generalist",
                    event_type=TraceEventType.THINKING,
                    action="answer_query",
                    reasoning_chunk=token,
                    details={},
                )
                # Attempt common pub/sub emit methods
                for method in ["publish", "emit", "broadcast", "notify", "dispatch"]:
                    if hasattr(telemetry_bus, method):
                        getattr(telemetry_bus, method)(event)
                        break

        return (
            full_response
            if full_response
            else "No response generated from the inference engine."
        )

    except Exception as e:
        logger.error(f"Inference failure during query: {e}")
        return f"The inference engine is currently unable to process general queries: {str(e)}"


async def handle_synthesize_rag(
    client: ollama.AsyncClient,
    model_name: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Synthesizes raw retrieved context with forced streaming."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    query = (
        payload_params.get("query")
        or payload_params.get("prompt")
        or payload_params.get("command")
        or getattr(payload, "query", None)
        or getattr(payload, "prompt", None)
        or params.get("query")
        or params.get("prompt")
        or params.get("command")
        or raw_prompt
        or "Synthesize retrieved intelligence."
    )
    context_raw = (
        payload_params.get("context")
        or params.get("context")
        or getattr(payload, "context", None)
        or ""
    )
    context = str(context_raw).strip()

    empty_indicators = {
        "", "none", "[]", "{}", "no explicit context provided.",
        "no relevant context found.", "no context found",
    }
    if not context or context.lower() in empty_indicators:
        logger.info("[GENERALIST] Synthesize RAG received empty context. Aborting inference pass.")
        msg = "I have searched the memory ledger, sir, but no relevant entries or project notes were found."
        if stream_callback:
            stream_callback(msg)
        return msg

    strict_rag_system = (
        f"{RAG_SYNTHESIS_PROMPT}\n\n"
        "STRICT GROUNDING DIRECTIVES:\n"
        "1. Answer strictly and exclusively using the provided RETRIEVED TECHNICAL CONTEXT below.\n"
        "2. Do NOT invent, assume, or extrapolate projects, dates, notes, or hardware details not explicitly stated.\n"
        "3. If the context does not contain sufficient details to fulfill the request, state clearly that the ledger lacks those specific details."
    )

    synthesis_prompt = (
        f"--- RETRIEVED TECHNICAL CONTEXT START ---\n"
        f"{context}\n"
        f"--- RETRIEVED TECHNICAL CONTEXT END ---\n\n"
        f"USER QUERY: {query}"
    )

    logger.info("The Generalist synthesizing RAG context...")

    try:
        full_response = ""
        # ---> FIX: ALWAYS STREAM <---
        async for chunk in await client.generate(
            model=model_name,
            prompt=synthesis_prompt,
            system=strict_rag_system,
            stream=True,
        ):
            token = chunk.get("response", "")
            full_response += token

            if stream_callback:
                stream_callback(token)
            else:
                event = TraceEvent(
                    agent_name="The_Generalist",
                    event_type=TraceEventType.THINKING,
                    action="synthesize_rag",
                    reasoning_chunk=token,
                    details={},
                )
                for method in ["publish", "emit", "broadcast", "notify", "dispatch"]:
                    if hasattr(telemetry_bus, method):
                        getattr(telemetry_bus, method)(event)
                        break

        return (
            full_response
            if full_response
            else "No synthesis output generated."
        )

    except Exception as e:
        logger.error(f"Failed to synthesize RAG context: {e}")
        return f"An error occurred while synthesizing retrieved knowledge: {str(e)}"


async def handle_get_system_info() -> str:
    """Gathers diagnostic info using system tool."""
    return get_system_info()


async def handle_execute_system_task(
    client: ollama.AsyncClient,
    model_name: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Translates NL requests if necessary and executes shell commands safely."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    command = (
        payload_params.get("command")
        or payload_params.get("cmd")
        or payload_params.get("prompt")
        or payload_params.get("query")
        or getattr(payload, "command", None)
        or getattr(payload, "prompt", None)
        or params.get("command")
        or params.get("cmd")
        or params.get("prompt")
        or params.get("query")
        or raw_prompt
    )
    if not command or not str(command).strip():
        return "Error: A 'command' or 'prompt' parameter is required for system tasks."

    command_str = str(command).strip()

    # Guardrail Intercept: Handoff document/GUI launching dynamically
    if any(re.search(pattern, command_str, re.IGNORECASE) for pattern in PLANNER_HANDOFF_PATTERNS):
        librarian = SkillLibrarian.get_instance()

        # Dynamically query the librarian for whichever agent currently owns the planning capability.
        # We use 'analyze_roadmap' as the anchor action based on your system route bootstrap.
        target_agent = "The_Planner"  # Fallback just in case the DB is completely empty

        action_details = librarian.get_action_details("analyze_roadmap")
        if action_details and "primary_agent_id" in action_details:
            target_agent = action_details["primary_agent_id"]
        else:
            # Secondary fallback: use the librarian's fuzzy matching if the exact action name was modified
            candidates = librarian.match_agents_for_prompt("analyze roadmap planning")
            if candidates:
                # Sort by match_score just in case (though Librarian already returns highest matches)
                target_agent = sorted(candidates, key=lambda x: x["match_score"], reverse=True)[0]["agent_id"]

        logger.warning(
            f"[GENERALIST GUARDRAIL] Intercepted desktop document request in system task handler: '{command_str}'. "
            f"Handing off to {target_agent}."
        )
        raise HandoffException(
            target_agent=target_agent,
            reason=f"Task involves document/GUI application execution requiring file discovery: {command_str}",
        )

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

    is_raw_cli = any(
        cmd_word in command_str.split() for cmd_word in KNOWN_CLI_EXECUTABLES
    ) or command_str.startswith(("/", "./", "~"))

    if not is_raw_cli:
        synth_prompt = (
            f"Convert the following natural language request into a single valid Linux bash command for Ubuntu.\n"
            f"Output ONLY the raw command text with no markdown formatting, commentary, or explanations.\n\n"
            f"Request: {command_str}"
        )
        try:
            response = await client.generate(
                model=model_name, prompt=synth_prompt
            )
            raw_synth = response.get("response", "").strip()
            clean_synth = re.sub(
                r"^```(?:bash|sh)?\s*", "", raw_synth, flags=re.IGNORECASE
            )
            clean_synth = re.sub(r"\s*```$", "", clean_synth).strip("` ")
            if clean_synth:
                logger.info(
                    f"Synthesized CLI command from NL input '{command_str}' -> '{clean_synth}'"
                )
                command_str = clean_synth
        except Exception as e:
            logger.error(
                f"Failed to synthesize CLI command from input: {e}"
            )

    return await execute_shell_command(
        command_str=command_str,
        timeout=timeout,
        stream_callback=stream_callback,
    )


async def handle_calculate_math(
    client: ollama.AsyncClient,
    model_name: str,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Evaluates mathematical expressions deterministically via AST or LLM assistance."""
    params = params or {}
    payload_params = (
        payload.params
        if isinstance(payload, DynamicActionPayload)
        else (payload if isinstance(payload, dict) else {})
    )
    expression = (
        payload_params.get("expression")
        or payload_params.get("math_expr")
        or payload_params.get("prompt")
        or payload_params.get("query")
        or getattr(payload, "expression", None)
        or getattr(payload, "prompt", None)
        or params.get("expression")
        or params.get("prompt")
        or params.get("math_expr")
        or params.get("query")
        or raw_prompt
    )
    if not expression or not str(expression).strip():
        return "Error: A mathematical expression is required for computation."

    expression_str = str(expression).strip()
    logger.info(f"The Generalist is computing: {expression_str}")

    # 1. Deterministic AST evaluation
    deterministic_result = safe_eval_math(expression_str)
    if deterministic_result is not None:
        res_str = f"Calculation Result: {deterministic_result}"
        if stream_callback:
            stream_callback(res_str)
        return res_str

    # 2. LLM fallback for reasoning/word problems
    system_prompt = (
        "You are a precise, deterministic mathematical engine. Evaluate the mathematical "
        "expression or problem provided in the prompt and output ONLY the final numerical result "
        "or concise mathematical output. Do not include conversational filler."
    )

    try:
        full_response = ""
        if stream_callback:
            async for chunk in await client.generate(
                model=model_name,
                system=system_prompt,
                prompt=expression_str,
                stream=True,
            ):
                token = chunk.get("response", "")
                full_response += token
                stream_callback(token)
        else:
            response = await client.generate(
                model=model_name,
                system=system_prompt,
                prompt=expression_str,
            )
            full_response = response.get("response", "").strip()

        return f"Calculation Result: {full_response.strip()}"
    except Exception as e:
        logger.error(f"Calculation failure: {e}")
        return f"Failed to compute the mathematical expression: {str(e)}"