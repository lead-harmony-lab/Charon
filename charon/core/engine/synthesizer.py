"""
charon/core/engine/synthesizer.py
System Version: v0.4.0 | File Revision: 3.0.0

Module: Response synthesis module via dynamic agent routing.
Updated to route synthesis directly through the 'synthesize' DB action SSOT.
"""

import inspect
import logging
from typing import Any, Callable, Optional

from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("Charon.Engine.Synthesizer")


class OutputSynthesizer:
    """Formulates specialist agent outputs into user-facing responses using dynamic agents."""

    def __init__(
        self,
        orchestrator: SessionGateway,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.orchestrator = orchestrator
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _get_synthesis_agent_id(self) -> str:
        """Queries the Librarian SSOT to determine the synthesis agent ID."""
        # 1. Look for explicit candidates authorized for the 'synthesize' action
        if hasattr(self.librarian, "get_agents_for_action"):
            agents = self.librarian.get_agents_for_action("synthesize")
            if agents:
                return agents[0]

        # 2. System generalist / planner fallback resolution
        generalist_id = self.librarian.resolve_agent_id_for_role("system_generalist")
        if generalist_id:
            return generalist_id

        # Fail Fast: Enforce database bootstrap integrity
        raise RuntimeError(
            "[FAIL-FAST] Mandatory 'synthesize' action or 'system_generalist' role not registered in database."
        )

    def _truncate_raw_output_for_context(self, text: str, max_chars: int = 6000) -> str:
        """Truncates raw output from the middle to prevent LLM context window overflows."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        truncated_count = len(text) - max_chars
        return (
            f"{text[:half]}\n\n"
            f"[... Charon Synthesis Guard: Truncated {truncated_count} raw characters ...]\n\n"
            f"{text[-half:]}"
        )

    async def synthesize(
        self,
        user_query: str,
        agent: str,
        raw_output: Any,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Synthesizes raw specialist tool outputs into clean, user-facing responses."""
        raw_str = str(raw_output) if raw_output is not None else ""

        if not raw_str.strip():
            return "Task executed successfully with no output returned."

        # Resolve display name for logger & prompt
        display_agent = (
            self.librarian.get_display_name_for_agent(agent)
            if hasattr(self.librarian, "get_display_name_for_agent")
            else str(agent)
        )

        logger.info(f"Synthesizing raw tool output from '{display_agent}'...")
        sanitized_context = self._truncate_raw_output_for_context(raw_str, max_chars=6000)

        try:
            # 1. Resolve agent authorized for action 'synthesize'
            synth_agent_id = self._get_synthesis_agent_id()

            # 2. Retrieve agent instance from dispatcher
            synth_agent = self.orchestrator.dispatcher._resolve_agent(synth_agent_id)

            # 3. Construct parameters targeting strict DB action 'synthesize'
            exec_kwargs = {
                "action": "synthesize",
                "parameters": {
                    "user_query": user_query,
                    "raw_output": raw_str,
                    "context": sanitized_context,
                    "executing_agent": display_agent,
                },
                "raw_prompt": user_query,
            }

            sig = inspect.signature(synth_agent.execute) if hasattr(synth_agent, "execute") else None
            if sig:
                has_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if "stream_cb" in sig.parameters or has_kwargs:
                    exec_kwargs["stream_cb"] = stream_cb
                elif "stream_callback" in sig.parameters:
                    exec_kwargs["stream_callback"] = stream_cb

            exec_res = synth_agent.execute(**exec_kwargs)
            synthesized = await exec_res if inspect.isawaitable(exec_res) else exec_res

            res_str = str(synthesized).strip() if synthesized else ""

            if not res_str:
                logger.warning(
                    f"Agent '{synth_agent_id}' returned empty synthesis. Falling back to raw output."
                )
                if stream_cb and raw_str:
                    stream_cb(f"{raw_str}\n")
                return raw_str

            return res_str

        except Exception as synth_err:
            logger.warning(f"Synthesis failed; returning raw execution output: {synth_err}")
            if stream_cb and raw_str:
                stream_cb(f"{raw_str}\n")
            return raw_str