"""
charon/concierge/autonomic.py
System Version: v3.6.0 | File Revision: 3.6.2

Manages Charon's internal biological rhythms, background task scheduling,
autonomic spontaneous interactions, and persistent alert debouncing via ChromaDB.
"""

import time
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from charon.gateway.routes.avatar import avatar_stream
from .scheduler import ConciergeScheduler

logger = logging.getLogger("Charon.UX.Autonomic")

# Default cooldown thresholds (seconds) by urgency level
URGENCY_COOLDOWNS = {
    "critical": 1800,   # 30 minutes (Level 3 - Vocal Warning)
    "warning": 7200,    # 2 hours (Level 2 - HUD Proposal Card)
    "info": 86400,      # 24 hours (Level 1 - HUD State Shift)
}

class TemporalContext:
    """Low-overhead temporal awareness for the Concierge."""
    def __init__(self):
        self._boot_ticks = time.monotonic()
        self.boot_timestamp = datetime.now(timezone.utc)
        self.last_interaction_ticks = self._boot_ticks
        self.autonomic_cycles = 0

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._boot_ticks

    @property
    def time_since_last_interaction(self) -> float:
        return time.monotonic() - self.last_interaction_ticks

    def mark_interaction(self):
        """Call this when the user explicitly interacts (voice, click, unlock)."""
        self.last_interaction_ticks = time.monotonic()

    def tick_cycle(self):
        """Called by the 5-second pulse to track active lifespan."""
        self.autonomic_cycles += 1


class AutonomicSystem:
    """Manages the biological clock, telemetry heartbeats, and spontaneous awareness loops."""

    def __init__(
        self,
        registry: Dict[str, Any],
        sensor: Any,
        speech_engine: Any,
        interaction_engine: Any,
        memory_collection: Optional[Any] = None,
        hospitality: Optional[Any] = None,
    ):
        self.registry = registry
        self.sensor = sensor
        self.speech_engine = speech_engine
        self.interactions = interaction_engine
        self.memory_collection = memory_collection
        self.hospitality = hospitality

        # Initialize the agent's sense of time
        self.temporal_context = TemporalContext()

        self.scheduler = ConciergeScheduler()
        self._configure_biological_clock()

    def _configure_biological_clock(self):
        """Schedules Charon's autonomic nervous system routines using registry intervals."""
        clock_cfg = self.registry.get("biological_clock", {})
        if not clock_cfg.get("enable_autonomic_scheduler", True):
            logger.info("Autonomic biological clock disabled by registry configuration.")
            return

        telemetry_sec = clock_cfg.get("telemetry_interval_seconds", 900)
        reflection_sec = clock_cfg.get("idle_heuristic_reflection_seconds", 86400)
        awareness_sec = clock_cfg.get("awareness_interval_seconds", 5)

        # 1. Heartbeat: Log telemetry at specified interval
        if hasattr(self.sensor, "capture_and_log_metrics"):
            self.scheduler.schedule_interval(
                interval_seconds=telemetry_sec, func=self.sensor.capture_and_log_metrics
            )

        # 2. Reflection (Sleep Cycle): Synthesize heuristics at specified interval
        if hasattr(self.sensor, "synthesize_idle_heuristic"):
            self.scheduler.schedule_interval(
                interval_seconds=reflection_sec, func=self.sensor.synthesize_idle_heuristic
            )

        # 3. The Pulse (Awareness Loop): Check environment for spontaneous interaction
        self.scheduler.schedule_interval(
            interval_seconds=awareness_sec, func=self._autonomic_awareness_check
        )

    async def start(self):
        """Starts background daemons."""
        clock_enabled = self.registry.get("biological_clock", {}).get("enable_autonomic_scheduler", True)
        if clock_enabled:
            self.scheduler.start()
            logger.info("Autonomic scheduling routines initiated.")

    def stop(self):
        """Halts background operations."""
        self.scheduler.stop()
        logger.info("Autonomic scheduling routines halted.")

    async def _autonomic_awareness_check(self):
        """
        The internal monologue. Evaluates desktop state and decides
        whether to spontaneously interact with the user via tiered alerts.
        """
        # --- TRACE LOG ---
        logger.debug("--- [Autonomic Pulse] Awareness loop triggered ---")

        if not self.registry.get("abilities", {}).get("spontaneous_speech", True):
            logger.debug("[Autonomic Pulse] Spontaneous speech disabled in registry. Bailing.")
            return

        # 1. TICK THE CLOCK
        self.temporal_context.tick_cycle()

        try:
            # 2. SENSE: Read the latest desktop state
            presence_state = {}
            if hasattr(self.sensor, "get_current_presence"):
                try:
                    presence_state = await self.sensor.get_current_presence()
                    logger.debug(f"[Autonomic Pulse] Presence state: {presence_state}")
                except Exception as sense_err:
                    logger.error(f"[Autonomic Pulse] Failed to sense presence: {sense_err}")
                    return
            else:
                logger.warning("[Autonomic Pulse] Sensor missing 'get_current_presence' method.")

            idle_time = presence_state.get("idle_time", 0)
            is_locked = presence_state.get("is_locked", False)
            just_unlocked = presence_state.get("unlocked_in_last_10s", False)

            # --- HOSPITALITY: EVALUATE RETURN ---
            if just_unlocked:
                logger.info("[Autonomic Pulse] System unlock detected. Evaluating hospitality routing.")
                self.temporal_context.mark_interaction()

                if self.hospitality:
                    # This will now route directly to avatar_stream.push_event
                    await self.hospitality.evaluate_user_return(idle_duration_seconds=idle_time)
                return
            # ------------------------------------

            # 3. EVALUATE & SUPPRESS: Tiered alert routing
            critical_alert = None
            if hasattr(self.sensor, "check_for_critical_alerts"):
                try:
                    critical_alert = await self.sensor.check_for_critical_alerts()
                    if critical_alert:
                        logger.info(f"[Autonomic Pulse] Critical alert found: {critical_alert.get('id')}")
                        await self._process_alert_with_memory(critical_alert)
                        return
                except Exception as alert_err:
                    logger.error(f"[Autonomic Pulse] Failed to check system alerts: {alert_err}")

            # SUPPRESSION GATE
            if is_locked or idle_time > 300:
                logger.debug(f"[Autonomic Pulse] Suppression gate active. Locked: {is_locked} | Idle Time: {idle_time}s")
                return

            logger.debug("[Autonomic Pulse] Passed suppression gate. Checking Level 1/2 heuristics...")

            # Level 2 IDE checks
            if hasattr(self.sensor, "get_ide_diagnostic_summary"):
                try:
                    ide_summary = self.sensor.get_ide_diagnostic_summary(lookback_seconds=180)
                    if ide_summary and ide_summary.get("error_count", 0) > 0:
                        logger.info(f"[Autonomic Pulse] IDE errors detected: {ide_summary.get('error_count')} errors.")
                        # ... (existing ide alert logic) ...
                        return
                except Exception as ide_err:
                    logger.error(f"[Autonomic Pulse] Failed to check IDE diagnostics: {ide_err}")

            # Level 1 Sub-threshold
            if hasattr(self.sensor, "get_ambient_load"):
                ambient_load = self.sensor.get_ambient_load()
                logger.debug(f"[Autonomic Pulse] Ambient load: {ambient_load}")
                if ambient_load > 0.85:
                    logger.info("[Autonomic Pulse] High ambient load detected. Pushing HUD visual state.")
                    await self._push_visual_state_change("concerned")
                    return

            logger.debug("[Autonomic Pulse] Pulse complete. No anomalies detected.")

        except Exception as e:
            logger.error(f"[Autonomic Pulse] Awareness loop encountered friction: {e}")

    async def _process_alert_with_memory(self, alert: Dict[str, Any]) -> None:
        """
        Evaluates system alerts against persistent ChromaDB memory to enforce
        debounce windows and generate contextual follow-up reminders.
        """
        summary = alert.get("summary", "a system anomaly was detected")
        urgency = alert.get("urgency", "critical").lower()
        alert_id_raw = alert.get("id", summary)
        alert_hash = hashlib.sha256(alert_id_raw.encode("utf-8")).hexdigest()[:16]
        doc_id = f"alert_state_{alert_hash}"
        actions = alert.get("actions", [])

        now_utc = datetime.now(timezone.utc)
        now_ts = now_utc.timestamp()

        alert_msg = f"Sir, forgive the intrusion, but {summary}."

        if not self.memory_collection:
            # Fallback to single push if vector memory is offline
            await self._route_alert(urgency, alert_msg, actions)
            return

        try:
            existing = self.memory_collection.get(ids=[doc_id])
            metadatas = existing.get("metadatas", [])

            if metadatas and len(metadatas) > 0 and metadatas[0]:
                meta = metadatas[0]
                last_notified = float(meta.get("last_notified", 0))
                notify_count = int(meta.get("notify_count", 1))

                cooldown = URGENCY_COOLDOWNS.get(urgency, URGENCY_COOLDOWNS["critical"])
                elapsed = now_ts - last_notified

                # Suppress if still within the debounce cooldown window
                if elapsed < cooldown:
                    return

                # Follow-up phrase for unresolved persistent alerts
                alert_msg = f"Sir, as a follow-up: {summary} is still unresolved."
                notify_count += 1
            else:
                notify_count = 1

            # Update persistent alert memory state
            self.memory_collection.upsert(
                ids=[doc_id],
                documents=[summary],
                metadatas=[{
                    "type": "autonomic_alert",
                    "urgency": urgency,
                    "last_notified": now_ts,
                    "last_notified_iso": now_utc.isoformat(),
                    "notify_count": notify_count,
                    "status": "unresolved"
                }]
            )

            await self._route_alert(urgency, alert_msg, actions)

        except Exception as e:
            logger.error(f"Failed to query/update alert state in ChromaDB: {e}")
            await self._route_alert(urgency, alert_msg, actions)

    async def _route_alert(self, urgency: str, text: str, actions: list):
        """Routes the alert to the appropriate escalation tier."""
        if urgency == "critical":
            await self._push_spontaneous_speech(text)
        elif urgency == "warning":
            await self._push_proposal_card(text, actions=actions)
        else:
            await self._push_visual_state_change("alert")

    async def _push_visual_state_change(self, emotion: str):
        """Escalation Level 1: Subtle visual HUD shift."""
        logger.info(f"Initiating visual state change: {emotion}")
        try:
            await avatar_stream.push_event("state_change", {"emotion": emotion})
        except Exception as e:
            logger.error(f"Failed to push visual state change: {e}")

    async def _push_proposal_card(self, text: str, actions: list = None, play_chime: bool = True):
        """Escalation Level 2: Interactive HUD proposal card."""
        logger.info(f"Initiating proposal card: '{text}'")
        try:
            await avatar_stream.push_event("proposal_card", {
                "text": text,
                "actions": actions or [{"label": "Acknowledge", "event": "dismiss"}],
                "play_chime": play_chime
            })
        except Exception as e:
            logger.error(f"Failed to push proposal card: {e}")

    async def _push_spontaneous_speech(self, text: str):
        """Escalation Level 3: Spontaneous synthesized speech."""
        logger.info(f"Initiating autonomic speech: '{text}'")
        try:
            # 1. Synthesize audio and visemes
            speech_data = await self.speech_engine.synthesize_speech(text=text)

            # 2. Push down the WebSocket to the GNOME extension
            await avatar_stream.push_event("spontaneous_speech", {
                "text": text,
                "audio_b64": speech_data.get("audio_b64"),
                "visemes": speech_data.get("visemes"),
                "duration": speech_data.get("duration", 0)
            })
        except Exception as e:
            logger.error(f"Failed to push spontaneous speech to avatar stream: {e}")