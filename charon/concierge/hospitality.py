"""
charon/concierge/hospitality.py
System Version: v3.6.5

Module: Concierge Hospitality Subroutine
"""
import asyncio
import logging
import datetime
from typing import Any, Callable, Optional
from charon.concierge.prompts import GREETING_SYSTEM_PROMPT
from charon.concierge.schemas import Modality

logger = logging.getLogger("Charon.Concierge.Hospitality")


class HospitalitySubroutine:
    def __init__(
        self,
        llm_client: Any,
        sensor: Any,
        broadcast_callback: Callable,
        model_name: str,
        process_callback: Optional[Callable] = None,
        ws_manager: Optional[Any] = None,
        memory: Optional[Any] = None
    ):
        self.llm_client = llm_client
        self.sensor = sensor
        self.broadcast = broadcast_callback
        self.process_callback = process_callback
        self.model_name = model_name
        self.ws_manager = ws_manager
        self.memory = memory

        self.SHORT_AWAY_THRESHOLD = 300  # 5 minutes
        self.EXTENDED_AWAY_THRESHOLD = 14400  # 4 hours

    async def execute_startup_greeting(self, recovered_tasks: int = 0) -> None:
        logger.info("[Hospitality] Triggering startup status update.")
        user_message = f"Context: [Startup] | Recovered Tasks: {recovered_tasks}"
        await self._generate_and_broadcast(user_message, "system_startup")

    async def evaluate_user_return(self, idle_duration_seconds: float) -> None:
        if idle_duration_seconds < self.SHORT_AWAY_THRESHOLD:
            return

        logger.info(f"[Hospitality] User returned after {idle_duration_seconds}s idle. Generating dynamic greeting.")

        # 1. Build the dynamic context payload
        telemetry_context = await self._gather_telemetry_context(idle_duration_seconds)

        # 2. Pass the raw telemetry to the LLM
        await self._generate_and_broadcast(
            user_message=telemetry_context,
            context="dynamic_return"
        )

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
        if not self.broadcast:
            logger.warning(f"[Hospitality] Broadcast callback not bound. Suppressing broadcast for {context}.")
            return

        if self.ws_manager:
            retries = 0
            while not getattr(self.ws_manager, "active_connections", None) and retries < 4:
                await asyncio.sleep(0.5)
                retries += 1

        # -------------------------------------------------------------
        # 1. EMIT PROCESS SIGNAL (Feeds GNOME Top-Bar Lane A)
        # -------------------------------------------------------------
        if context == "system_startup":
            process_msg = "Composing welcome message..."
        elif context == "dynamic_return":
            process_msg = "Analyzing telemetry context..."
        else:
            process_msg = "Drafting greeting..."

        if self.process_callback:
            if asyncio.iscoroutinefunction(self.process_callback):
                await self.process_callback(process_msg, context=context, status="working")
            else:
                self.process_callback(process_msg, context=context, status="working")

        try:
            # -------------------------------------------------------------
            # 2. GENERATE GREETING
            # -------------------------------------------------------------
            response = await self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": GREETING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=150
            )

            greeting_text = response.choices[0].message.content.strip()
            logger.debug(f"[Hospitality] Broadcasting greeting: {greeting_text}")

            # -------------------------------------------------------------
            # 3. EMIT DIALOGUE SIGNAL (Feeds GTK4 Avatar Lane B)
            # -------------------------------------------------------------
            if asyncio.iscoroutinefunction(self.broadcast):
                await self.broadcast(greeting_text, context=context, modality=Modality.DIALOGUE)
            else:
                self.broadcast(greeting_text, context=context, modality=Modality.DIALOGUE)

            # -------------------------------------------------------------
            # 4. RESET PROCESS SIGNAL (Clears GNOME Top-Bar)
            # -------------------------------------------------------------
            if self.process_callback:
                if asyncio.iscoroutinefunction(self.process_callback):
                    await self.process_callback("active", context="idle", status="active")
                else:
                    self.process_callback("active", context="idle", status="active")

        except Exception as e:
            logger.error(f"[Hospitality] Failed to generate/broadcast greeting for {context}: {e}")
            # Reset top-bar on failure
            if self.process_callback:
                if asyncio.iscoroutinefunction(self.process_callback):
                    await self.process_callback("active", context="error", status="error")
                else:
                    self.process_callback("active", context="error", status="error")

    async def _gather_telemetry_context(self, idle_duration_seconds: float) -> str:
        if not self.sensor:
            return "Context unavailable: TelemetrySensor not linked."

        # Calculate exact time the user went idle
        idle_since_dt = datetime.datetime.now() - datetime.timedelta(seconds=idle_duration_seconds)
        idle_since_iso = idle_since_dt.isoformat()

        # 1. Fetch Ledger Deltas (Background activity while away)
        try:
            ledger_deltas = await self.sensor.get_session_deltas(idle_since_iso)
            bg_tasks = ledger_deltas.get("task_count", 0)
            bg_alerts = ledger_deltas.get("alert_count", 0)
        except Exception as e:
            logger.warning(f"[Hospitality] Failed to fetch ledger deltas: {e}")
            bg_tasks, bg_alerts = 0, 0

        # 2. Hardware & System Metrics
        metrics = self.sensor.capture_and_log_metrics()
        cpu = metrics.get("cpu_percent", 0)
        ram = metrics.get("memory_percent", 0)

        # 3. Alerts & Harness State
        harness_state = self.sensor.harness_state.value if hasattr(self.sensor, "harness_state") else "UNKNOWN"
        alerts = await self.sensor.check_for_critical_alerts()
        alert_text = alerts["summary"] if alerts else "Nominal"

        # 4. Sensory Desktop Context
        desktop_context = self.sensor.get_recent_desktop_context(minutes_lookback=15)

        # 5. Semantic Memory Context
        mem_context = await self._gather_memory_context()

        # 6. Absence & Time Calculation
        hours_away = round(idle_duration_seconds / 3600, 2)
        absence_status = "Brief Step-Away" if hours_away < 1 else f"Extended Absence ({hours_away} hours)"
        local_time = datetime.datetime.now().strftime("%I:%M %p")

        # 7. Construct prompt block
        telemetry_block = f"""
        CURRENT SYSTEM STATE:
        - Local Time: {local_time}
        - User Status: Returned from {absence_status}
        - Harness State: {harness_state}
        - System Load: CPU {cpu}%, RAM {ram}%
        - Active Critical Alerts: {alert_text}

        BACKGROUND ACTIVITY (While Away):
        - Background Tasks Completed: {bg_tasks}
        - Background Task Faults: {bg_alerts}

        SENSORY & DESKTOP CONTEXT:
        - Recent Desktop Focus: {desktop_context}

        MEMORY CONTEXT:
        - Recent Ephemeral Actions: {mem_context.get('active_project')}
        - Pre-Departure State: {mem_context.get('recent_sentiment', 'neutral')}
        - Known User Preferences: {mem_context.get('user_preferences')}
        """
        return telemetry_block.strip()

    async def _gather_memory_context(self) -> dict:
        """Extracts recent actions and long-term interaction heuristics."""
        context = {
            "active_project": "General Operations",
            "recent_sentiment": "neutral",
            "user_preferences": "None specific"
        }

        if not self.memory:
            return context

        try:
            # 1. Query Ephemera (Short-term memory: What were they just doing?)
            recent_logs = await self.memory.query_ephemera(limit=3)
            if recent_logs:
                context["active_project"] = " | ".join([log.get('summary', '') for log in recent_logs])

                # Simple heuristic: if recent logs contain error keywords, flag it
                if any(err in context["active_project"].lower() for err in ["error", "fail", "exception"]):
                    context["recent_sentiment"] = "frustrated / debugging"

            # 2. Query Heuristics (Long-term memory: How do they like to be addressed?)
            heuristics = await self.memory.query_heuristics(query="greeting preferences and tone")
            if heuristics:
                context["user_preferences"] = heuristics.get('summary', context["user_preferences"])

        except Exception as e:
            logger.warning(f"[Hospitality] Semantic memory retrieval failed: {e}")

        return context