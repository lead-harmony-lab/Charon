"""
charon/core/engine/self_healing.py
System Version: v0.3.0 | File Revision: 2.2.0

Module: Diagnostic intercept and self-healing handler for Charon.
Refactored to query system_roles schema directly and raise explicit fail-fast
runtime errors if mandatory roles are unbound.
"""

import inspect
import logging
from typing import Callable, Optional, Union

from charon.core.ledger import ExecutionLedger
from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian

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
        if hasattr(self.librarian, "resolve_agent_id_for_action"):
            diag_agent = self.librarian.resolve_agent_id_for_action("diagnose")
            if diag_agent:
                return diag_agent

        # 2. Prefer system_engineer role for diagnostic execution
        engineer_id = self.librarian.resolve_agent_id_for_role("system_engineer")
        if engineer_id:
            return engineer_id

        # 3. Secondary system_planner fallback
        planner_id = self.librarian.resolve_agent_id_for_role("system_planner")
        if planner_id:
            return planner_id

        # Fail Fast: Raise explicit error rather than hallucinating fallbacks
        raise RuntimeError(
            "Bootstrap Error: Neither 'system_engineer' nor 'system_planner' mandatory "
            "roles could be resolved in system_roles for self-healing diagnostics."
        )

    async def handle_if_needed(
        self,
        step_num: Union[int, str],
        agent_name: str,
        step_result: str,
        raw_prompt: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Inspects step results for failure indicators and invokes a diagnostic action."""
        if not step_result:
            return step_result

        # Explicit Authorization & Dependency Guardrails
        auth_prefixes = (
            "[Awaiting Authorization]",
            "[Authorization Denied]",
            "[Authorization Error]",
            "[Dependency Error]",
            "[System Error]",
        )
        if any(step_result.startswith(prefix) for prefix in auth_prefixes):
            logger.debug(
                f"Step {step_num} result indicates policy/status control ({step_result[:30]}). "
                f"Bypassing self-healing diagnosis."
            )
            return step_result

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
        has_error = any(trigger.lower() in step_result.lower() for trigger in failure_triggers)

        if not has_error:
            return step_result

        logger.warning(f"Step {step_num} ({agent_name}) hit an execution issue. Initiating self-healing...")

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="step_self_healing_triggered",
                data={"step": step_num, "agent": agent_name, "error_preview": step_result[:300]},
            )

        if stream_cb:
            stream_cb("\n⚠️ *Step execution failed. Intercepting log output for self-healing diagnosis...*\n")

        try:
            diagnostic_agent_id = self._resolve_diagnostic_agent()
            diagnostic_agent = self.orchestrator.dispatcher._resolve_agent(diagnostic_agent_id)

            # Build execution kwargs and reflectively inject stream callback
            exec_kwargs = {
                "action": "diagnose",
                "parameters": {
                    "log_content": step_result,
                    "failing_agent": agent_name,
                    "step_num": step_num,
                },
                "raw_prompt": raw_prompt,
            }

            sig = inspect.signature(diagnostic_agent.execute) if hasattr(diagnostic_agent, "execute") else None
            if sig:
                if "stream_cb" in sig.parameters:
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

            return f"{step_result}\n\n[Self-Healing Recovery Intercept]:\n{diagnosis}"

        except Exception as diag_err:
            logger.error(f"Failed to execute self-healing diagnosis: {diag_err}", exc_info=True)
            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="step_self_healing_failed",
                    data={"step": step_num, "error": str(diag_err)},
                )
            return f"{step_result}\n\n[Self-Healing Failed]: {str(diag_err)}"