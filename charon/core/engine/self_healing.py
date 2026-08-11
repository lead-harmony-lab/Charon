"""
charon/core/engine/self_healing.py
System Version: v0.6.3 | File Revision: 4.0.0

Module: Diagnostic intercept and self-healing handler for Charon.
Refactored to query system_roles schema directly, raise explicit fail-fast
runtime errors if mandatory roles are unbound, and protect context limits.
Enforces direct librarian role/action resolution without defensive hasattr checks.
"""

import inspect
import logging
from typing import Any, Callable, Optional, Union

from charon.core.ledger import ExecutionLedger
from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Engine.SelfHealing")


class SelfHealingHandler:
    """Inspects step outputs for execution errors and dispatches diagnostic tasks dynamically."""

    def __init__(
        self,
        orchestrator: SessionGateway,
        ledger: Optional[ExecutionLedger] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.orchestrator = orchestrator
        self.ledger = ledger
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_diagnostic_agent(self) -> str:
        """Dynamically query the Librarian for the agent assigned to diagnostics."""
        # 1. Action-based dynamic resolution
        try:
            diag_agent = self.librarian.resolve_agent_id_for_action("diagnose")
            if diag_agent:
                return diag_agent
        except RoleResolutionError:
            pass

        # 2. Prefer system_engineer role for diagnostic execution
        try:
            engineer_id = self.librarian.resolve_agent_id_for_role("system_engineer")
            if engineer_id:
                return engineer_id
        except RoleResolutionError:
            pass

        # 3. Secondary system_planner fallback
        try:
            planner_id = self.librarian.resolve_agent_id_for_role("system_planner")
            if planner_id:
                return planner_id
        except RoleResolutionError:
            pass

        # Fail Fast: Raise explicit error rather than hallucinating fallbacks
        raise RuntimeError(
            "Bootstrap Error: Neither 'system_engineer' nor 'system_planner' mandatory "
            "roles could be resolved in system_roles for self-healing diagnostics."
        )

    def _truncate_log_for_context(self, log_text: str, max_chars: int = 4000) -> str:
        """Truncates diagnostic log content to fit comfortably within model context windows."""
        if len(log_text) <= max_chars:
            return log_text
        half = max_chars // 2
        truncated_count = len(log_text) - max_chars
        return (
            f"{log_text[:half]}\n\n"
            f"[... Charon Self-Healing Context Guard: Truncated {truncated_count} log characters ...]\n\n"
            f"{log_text[-half:]}"
        )

    async def handle_if_needed(
        self,
        step_num: Union[int, str],
        agent_name: str,
        step_result: Any,
        raw_prompt: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Inspects step results for failure indicators and invokes a diagnostic action."""
        if step_result is None:
            return ""

        step_result_str = str(step_result)
        if not step_result_str.strip():
            return step_result_str

        # Explicit Authorization & Dependency Guardrails / Loop Prevention
        auth_prefixes = (
            "[Awaiting Authorization]",
            "[Authorization Denied]",
            "[Authorization Error]",
            "[Dependency Error]",
            "[System Error]",
        )
        if any(step_result_str.startswith(prefix) for prefix in auth_prefixes) or "[Self-Healing" in step_result_str:
            logger.debug(
                f"Step {step_num} result indicates policy/status control or existing diagnosis. "
                f"Bypassing self-healing diagnosis."
            )
            return step_result_str

        failure_triggers = [
            "[Runtime Error]",
            "Execution aborted",
            "command not found",
            "Traceback (most recent call last)",
            "SyntaxError:",
            "TypeError:",
            "KeyError:",
            "NameError:",
        ]
        has_error = any(trigger.lower() in step_result_str.lower() for trigger in failure_triggers)

        if not has_error:
            return step_result_str

        logger.warning(f"Step {step_num} ({agent_name}) hit an execution issue. Initiating self-healing...")

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="step_self_healing_triggered",
                data={"step": step_num, "agent": agent_name, "error_preview": step_result_str[:300]},
            )

        if stream_cb:
            stream_cb("\n⚠️ *Step execution failed. Intercepting log output for self-healing diagnosis...*\n")

        try:
            diagnostic_agent_id = self._resolve_diagnostic_agent()
            diagnostic_agent = self.orchestrator.dispatcher._resolve_agent(diagnostic_agent_id)

            sanitized_log = self._truncate_log_for_context(step_result_str, max_chars=4000)

            # Build execution kwargs
            exec_kwargs = {
                "action": "diagnose",
                "parameters": {
                    "log_content": sanitized_log,
                    "failing_agent": agent_name,
                    "step_num": step_num,
                },
                "raw_prompt": raw_prompt,
            }

            # Inspect signature including **kwargs support
            execute_fn = getattr(diagnostic_agent, "execute", None)
            sig = inspect.signature(execute_fn) if execute_fn else None
            if sig:
                has_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if "stream_cb" in sig.parameters or has_kwargs:
                    exec_kwargs["stream_cb"] = stream_cb
                elif "stream_callback" in sig.parameters:
                    exec_kwargs["stream_callback"] = stream_cb

            diag_res = diagnostic_agent.execute(**exec_kwargs)
            diagnosis = await diag_res if inspect.isawaitable(diag_res) else diag_res

            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="step_self_healing_resolved",
                    data={"step": step_num, "diagnosis_preview": str(diagnosis)[:300]},
                )

            return f"{step_result_str}\n\n[Self-Healing Recovery Intercept]:\n{diagnosis}"

        except Exception as diag_err:
            logger.error(f"Failed to execute self-healing diagnosis: {diag_err}", exc_info=True)
            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="step_self_healing_failed",
                    data={"step": step_num, "error": str(diag_err)},
                )
            return f"{step_result_str}\n\n[Self-Healing Failed]: {str(diag_err)}"