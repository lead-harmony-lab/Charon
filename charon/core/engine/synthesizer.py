"""
charon/core/engine/synthesizer.py
System Version: v0.3.1 | File Revision: 2.2.0

Module: Response synthesis module via dynamic agent routing.
Patched to inspect variadic keyword arguments (**kwargs) for streaming callbacks,
guarantee CLI output delivery on fallback, and enforce fail-fast system role resolution.
"""

import inspect
import logging
from typing import Callable, Optional

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
        """Queries the Librarian to dynamically determine the synthesis agent."""
        # 1. Direct action resolution via Librarian
        if hasattr(self.librarian, "resolve_agent_id_for_action"):
            synth_agent = self.librarian.resolve_agent_id_for_action("synthesize")
            if synth_agent:
                return synth_agent

        # 2. System generalist role resolution (matches system_roles table key)
        generalist_id = self.librarian.resolve_agent_id_for_role("system_generalist")
        if generalist_id:
            return generalist_id

        # Fail Fast: Enforce database bootstrap integrity
        raise RuntimeError(
            "Bootstrap Error: Mandatory system role 'system_generalist' is not bound in system_roles."
        )

    async def synthesize(
        self,
        user_query: str,
        agent: str,
        raw_output: str,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Synthesizes raw specialist tool outputs into clean, user-facing responses."""
        if not raw_output or not raw_output.strip():
            return "Task executed successfully with no output returned."

        # Resolve display name for logger & prompt if input is an agent ID or role
        display_agent = (
            self.librarian.get_display_name_for_agent(agent)
            if hasattr(self.librarian, "get_display_name_for_agent")
            else agent
        )

        logger.info(f"Synthesizing raw tool output from '{display_agent}'...")

        synthesis_prompt = (
            f"User Prompt: {user_query}\n"
            f"Executing Specialist: {display_agent}\n"
            f"Raw Execution Data:\n```\n{raw_output}\n```\n\n"
            "Synthesize this execution output into a concise, well-formatted response for the user. "
            "Do not describe what you are doing—just present the final result directly."
        )

        try:
            # 1. Dynamically resolve synthesis agent
            synth_agent_id = self._get_synthesis_agent_id()

            # 2. Retrieve agent instance from dispatcher
            synth_agent = self.orchestrator.dispatcher._resolve_agent(synth_agent_id)

            # 3. Construct execution parameters and inspect streaming signature
            exec_kwargs = {
                "action": "synthesize",
                "parameters": {
                    "prompt": synthesis_prompt,
                    "context": raw_output,
                    "raw_output": raw_output,
                    "user_query": user_query,
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
                    f"Agent '{synth_agent_id}' returned empty synthesis output. Falling back to raw tool output."
                )
                if stream_cb and raw_output:
                    stream_cb(f"{raw_output}\n")
                return raw_output

            return res_str

        except Exception as synth_err:
            logger.warning(
                f"Output synthesis failed; returning raw execution output: {synth_err}"
            )
            if stream_cb and raw_output:
                stream_cb(f"{raw_output}\n")
            return raw_output