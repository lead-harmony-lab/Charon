"""
Skill: System Log Analyzer
Description: Diagnostic engine for parsing compilation, error, and system execution logs.
"""

import logging
from typing import Any, Callable, Dict, Optional, Union

import ollama

logger = logging.getLogger("charon.skills.sys_log_analyzer")

DIAGNOSTICS_SYSTEM_PROMPT = (
    "You are an expert diagnostic system. Analyze the provided error log. "
    "Identify the root cause of the failure and provide a direct, actionable solution. "
    "Do not output conversational filler; provide strictly the diagnosis and the fix."
)


def _extract_param_dict(payload: Optional[Union[Dict[str, Any], Any]]) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload.get("params", payload)
    elif payload and hasattr(payload, "params"):
        return payload.params or {}
    return {}


def resolve_log_content(
    params: Dict[str, Any],
    raw_prompt: str = "",
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> str:
    """Multi-tier fallback extraction for error log text."""
    p_dict = _extract_param_dict(payload)

    log_data = (
        params.get("log_content")
        or params.get("logs")
        or params.get("error_log")
        or p_dict.get("log_content")
        or p_dict.get("logs")
        or p_dict.get("error_log")
        or getattr(payload, "log_content", None)
        or getattr(payload, "logs", None)
    )
    if log_data:
        return str(log_data).strip()

    return raw_prompt.strip() if raw_prompt else ""


async def analyze_error_logs(
    client: ollama.AsyncClient,
    model_name: str,
    params: Dict[str, Any],
    raw_prompt: str = "",
    stream_callback: Optional[Callable[[str], None]] = None,
    payload: Optional[Union[Dict[str, Any], Any]] = None,
) -> Dict[str, Any]:
    """Analyzes error matrix logs and yields root cause diagnosis."""
    log_content = resolve_log_content(params, raw_prompt=raw_prompt, payload=payload)
    cb = stream_callback or params.get("stream_callback")

    if not log_content:
        return {"status": "error", "error": "Error: 'log_content' is required for analysis."}

    logger.info("[LogAnalyzer] Executing diagnostic evaluation...")

    try:
        analysis = ""
        if cb:
            async for chunk in await client.generate(
                model=model_name,
                system=DIAGNOSTICS_SYSTEM_PROMPT,
                prompt=f"Log Content:\n{log_content}",
                stream=True,
            ):
                token = chunk.get("response", "")
                analysis += token
                cb(token)
        else:
            response = await client.generate(
                model=model_name,
                system=DIAGNOSTICS_SYSTEM_PROMPT,
                prompt=f"Log Content:\n{log_content}",
            )
            analysis = response.get("response", "").strip()

        formatted_result = f"Log Analysis:\n\n{analysis.strip()}"
        return {"status": "success", "result": formatted_result}

    except Exception as e:
        logger.error(f"[LogAnalyzer] Failure during log diagnosis: {e}")
        return {"status": "error", "error": f"Failed to analyze logs: {str(e)}"}