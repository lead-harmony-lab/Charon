"""
charon/concierge/hospitality.py
System Version: v3.6.5

Module: Concierge Hospitality Subroutine
"""
import asyncio
import logging
from typing import Any, Optional
from charon.concierge.prompts import GREETING_SYSTEM_PROMPT

logger = logging.getLogger("Charon.Concierge.Hospitality")


class HospitalitySubroutine:
    def __init__(self, llm_client: Any, ws_manager: Optional[Any] = None, memory: Optional[Any] = None):
        self.llm_client = llm_client
        self.ws_manager = ws_manager
        self.memory = memory
        self.concierge = None  # Will be injected by core.py during initialization

        self.SHORT_AWAY_THRESHOLD = 300  # 5 minutes
        self.EXTENDED_AWAY_THRESHOLD = 14400  # 4 hours

    async def execute_startup_greeting(self, recovered_tasks: int = 0) -> None:
        logger.info("[Hospitality] Triggering startup status update.")
        user_message = f"Context: [Startup] | Recovered Tasks: {recovered_tasks}"
        await self._generate_and_broadcast(user_message, "system_startup")

    async def evaluate_user_return(self, idle_duration_seconds: float) -> None:
        if idle_duration_seconds < self.SHORT_AWAY_THRESHOLD:
            return

        logger.info(f"[Hospitality] User returned after {idle_duration_seconds}s idle.")

        if idle_duration_seconds >= self.EXTENDED_AWAY_THRESHOLD:
            await self._handle_extended_return(idle_duration_seconds)
        else:
            await self._handle_short_return()

    async def _handle_short_return(self) -> None:
        user_message = "Context: [Short Return]"
        await self._generate_and_broadcast(user_message, "short_return")

    async def _handle_extended_return(self, idle_duration: float) -> None:
        hours_away = round(idle_duration / 3600, 1)
        active_project = "their ongoing work"

        if self.memory and hasattr(self.memory, "get_recent_context"):
            recent = await self.memory.get_recent_context()
            if recent:
                active_project = recent

        user_message = f"Context: [Extended Return] | Hours Away: {hours_away} | Active Project: {active_project}"
        await self._generate_and_broadcast(user_message, "extended_return")

    async def _generate_and_broadcast(self, user_message: str, context: str) -> None:
        """
        Generates a context-aware greeting using the LLM and emits it
        via the central Concierge multimodal dual pathway.
        """
        if not self.concierge:
            logger.warning(f"[Hospitality] Concierge reference not bound. Suppressing broadcast for {context}.")
            return

        # --- RACE CONDITION FIX ---
        # Poll for an active UI connection for up to 5 seconds
        if self.ws_manager:
            retries = 0
            while not getattr(self.ws_manager, "active_connections", None) and retries < 10:
                await asyncio.sleep(0.5)
                retries += 1

            if not getattr(self.ws_manager, "active_connections", None):
                logger.warning(f"[Hospitality] No UI connected after 5s. Aborting {context} greeting.")
                return

        try:
            # Generate the greeting
            model_name = self.concierge.model_name if self.concierge else "llama3.1"

            response = await self.llm_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": GREETING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=150
            )

            greeting_text = response.choices[0].message.content.strip()

            logger.debug(f"[Hospitality] Broadcasting greeting: {greeting_text}")
            await self.concierge.broadcast(greeting_text, context=context)

        except Exception as e:
            logger.error(f"[Hospitality] Failed to generate/broadcast greeting for {context}: {e}")