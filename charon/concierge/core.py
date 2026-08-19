"""
charon/concierge/core.py
System Version: v3.0.0 | File Revision: 3.0.0

Module: Core Concierge Service
Orchestrates dynamic greetings, LLM-driven proactive follow-up proposals,
payload wrapping, and internal background task scheduling (biological clock).
"""

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import chromadb
from pydantic import ValidationError

from charon.config.paths import CONCIERGE_MEMORY_DIR

from .constants import EXIT_PHRASES, TRIVIAL_QUERY_PATTERNS
from .memory import SemanticMemory
from .prompts import (
    CONCIERGE_SYSTEM_PROMPT,
    GREETING_SYSTEM_PROMPT,
    PAYLOAD_WRAPPER_PROMPT,
)
from .scheduler import ConciergeScheduler
from .schemas import ConciergeProposal, ConciergeResponse
from .telemetry import TelemetrySensor

logger = logging.getLogger("Charon.UX.Concierge")

DEFAULT_REGISTRY_PATH = Path("charon/config/registry/concierge.json")


class ConciergeService:
    """Manages proactive next-step proposals, dynamic greetings, and internal biological rhythms."""

    def __init__(
        self,
        llm_client: Any,
        model_name: Optional[str] = None,
        min_confidence: Optional[float] = None,
        registry_path: Optional[Path] = None,
    ):
        self.client = llm_client
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH
        self.registry = self._load_registry()

        # Extract config from JSON registry with explicit argument overrides
        model_cfg = self.registry.get("model_settings", {})
        self.model_name = model_name or model_cfg.get("model_name", "llama3.1")
        self.min_confidence = (
            min_confidence if min_confidence is not None else model_cfg.get("min_confidence_threshold", 0.7)
        )
        self.temp_greeting = model_cfg.get("temperature_greeting", 0.6)
        self.temp_proposal = model_cfg.get("temperature_proposal", 0.2)
        self.temp_chat = model_cfg.get("temperature_chat", 0.7)

        self.sensor = TelemetrySensor()

        # 1. Initialize ONE shared ChromaDB client for the Concierge
        memory_cfg = self.registry.get("memory_settings", {})
        ephemera_col = memory_cfg.get("chroma_collection_ephemera", "concierge_ephemera")
        heuristics_col = memory_cfg.get("chroma_collection_heuristics", "core_heuristics")

        try:
            self.chroma_client = chromadb.PersistentClient(path=str(CONCIERGE_MEMORY_DIR))
            self.memory_collection = self.chroma_client.get_or_create_collection(name=ephemera_col)
            self.heuristics_collection = self.chroma_client.get_or_create_collection(name=heuristics_col)
            logger.info(f"Concierge memory initialized at {CONCIERGE_MEMORY_DIR}")
        except Exception as e:
            logger.error(f"Failed to initialize Concierge memory: {e}")
            self.chroma_client = None
            self.memory_collection = None
            self.heuristics_collection = None

        # 2. Pass the shared client to SemanticMemory
        self.memory = SemanticMemory(
            llm_client=self.client,
            model_name=self.model_name,
            chroma_client=self.chroma_client,
        )

        # 3. Initialize and configure the Internal Biological Clock
        self.scheduler = ConciergeScheduler()
        self._configure_biological_clock()

    def _load_registry(self) -> Dict[str, Any]:
        """Loads central configuration settings from JSON registry."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    logger.info(f"Loaded registry configuration from {self.registry_path}")
                    return config
            except Exception as e:
                logger.error(f"Failed to read registry at {self.registry_path}: {e}")
        else:
            logger.warning(f"Registry file not found at {self.registry_path}. Using internal defaults.")
        return {}

    def reload_registry(self) -> None:
        """Hot-reloads configuration options from disk."""
        self.registry = self._load_registry()
        model_cfg = self.registry.get("model_settings", {})
        self.model_name = model_cfg.get("model_name", self.model_name)
        self.min_confidence = model_cfg.get("min_confidence_threshold", self.min_confidence)
        self.temp_greeting = model_cfg.get("temperature_greeting", self.temp_greeting)
        self.temp_proposal = model_cfg.get("temperature_proposal", self.temp_proposal)
        self.temp_chat = model_cfg.get("temperature_chat", self.temp_chat)
        logger.info("Concierge registry parameters successfully reloaded.")

    def _configure_biological_clock(self):
        """Schedules Charon's autonomic nervous system routines using registry intervals."""
        clock_cfg = self.registry.get("biological_clock", {})
        if not clock_cfg.get("enable_autonomic_scheduler", True):
            logger.info("Autonomic biological clock disabled by registry configuration.")
            return

        telemetry_sec = clock_cfg.get("telemetry_interval_seconds", 900)
        reflection_sec = clock_cfg.get("idle_heuristic_reflection_seconds", 86400)

        # Heartbeat: Log telemetry at specified interval
        self.scheduler.schedule_interval(
            interval_seconds=telemetry_sec, func=self.sensor.capture_and_log_metrics
        )

        # Reflection (Sleep Cycle): Synthesize heuristics at specified interval
        self.scheduler.schedule_interval(
            interval_seconds=reflection_sec, func=self.sensor.synthesize_idle_heuristic
        )

    async def awaken(self):
        """Starts background daemons. Call this when spinning up the Charon process."""
        clock_enabled = self.registry.get("biological_clock", {}).get("enable_autonomic_scheduler", True)
        if clock_enabled:
            self.scheduler.start()
        abilities = self.registry.get("abilities", {})
        logger.info(f"The Continental is online. Charon is awake. Active abilities: {abilities}")

    async def sleep(self):
        """Gracefully halts background operations."""
        self.scheduler.stop()
        logger.info("Charon has entered standby.")

    def _get_active_heuristics(self) -> str:
        """Fetches all learned behaviors from the semantic memory bank."""
        if not self.heuristics_collection:
            return ""

        try:
            results = self.heuristics_collection.get()
            if results and results.get("documents"):
                rules = "\n".join([f"- {doc}" for doc in results["documents"]])
                return f"\nLEARNED BEHAVIORAL DIRECTIVES:\n{rules}\n"
        except Exception as e:
            logger.debug(f"Failed to fetch heuristics: {e}")
        return ""

    async def generate_greeting(self, user_id: str = "default") -> str:
        """Generates a dynamic greeting based on temporal and systemic deltas."""
        if not self.registry.get("abilities", {}).get("briefings", True):
            return "Welcome to The Continental."

        now = datetime.datetime.now()
        warmth_hours = self.registry.get("memory_settings", {}).get("session_delta_warmth_hours", 12.0)

        # 1. Fetch the last briefing state from episodic memory
        last_briefing_doc = {
            "timestamp": (now - datetime.timedelta(days=1)).isoformat(),
            "task_count": 0,
            "alert_count": 0,
        }
        memory_id = f"{user_id}_last_briefing"

        if self.memory_collection:
            try:
                result = self.memory_collection.get(ids=[memory_id])
                if result and result.get("documents") and len(result["documents"]) > 0:
                    last_briefing_doc = json.loads(result["documents"][0])
            except Exception as e:
                logger.debug(f"Could not fetch concierge memory, defaulting to cold start: {e}")

        last_time = datetime.datetime.fromisoformat(last_briefing_doc["timestamp"])
        hours_since_last = (now - last_time).total_seconds() / 3600.0

        # 2. Query the TelemetrySensor for actual session deltas
        try:
            deltas = await self.sensor.get_session_deltas(last_briefing_doc["timestamp"])
            current_task_count = deltas.get("task_count", 0)
            current_alert_count = deltas.get("alert_count", 0)
        except Exception as e:
            logger.error(f"Failed to fetch session deltas from ledger: {e}")
            current_task_count = 0
            current_alert_count = 0

        # 3. Determine Briefing Context based on actual deltas
        has_new_tasks = current_task_count > 0
        has_new_alerts = current_alert_count > 0

        if hours_since_last < warmth_hours and not (has_new_tasks or has_new_alerts):
            logger.debug(f"Briefing bypassed. Session is warm (< {warmth_hours}h) with no state delta.")
            context_str = "Context: [Continuation] | Active Session | No new events"
            should_update_memory = False

        elif hours_since_last < warmth_hours and has_new_alerts:
            logger.debug("Session warm, but new alerts detected. Triggering targeted notification.")
            context_str = f"Context: [Continuation] | Active Session | {current_alert_count} New Alert(s)"
            should_update_memory = True

        else:
            logger.debug("Triggering full system briefing.")
            context_str = (
                f"Context: [Full Briefing] | "
                f"{current_task_count} New Task(s) | {current_alert_count} New Alert(s)"
            )
            should_update_memory = True

        # 4. Generate Persona Greeting
        prompt = f"{context_str}\nGenerate greeting:"
        try:
            response = await self.client.generate(
                model=self.model_name,
                system=GREETING_SYSTEM_PROMPT,
                prompt=prompt,
                options={"temperature": self.temp_greeting},
            )
            greeting_text = response.get("response", "Welcome to The Continental.").strip('"')
        except Exception as e:
            logger.error(f"Failed to generate greeting: {e}")
            greeting_text = "Welcome to The Continental. How may I be of service?"

        # 5. Update Memory to reset the clock if a briefing was provided
        if should_update_memory and self.memory_collection:
            new_state = {
                "timestamp": now.isoformat(),
                "task_count": current_task_count,
                "alert_count": current_alert_count,
            }
            try:
                self.memory_collection.upsert(
                    ids=[memory_id],
                    documents=[json.dumps(new_state)],
                    metadatas=[{"type": "state_snapshot"}],
                )
            except Exception as e:
                logger.error(f"Failed to save concierge memory state: {e}")

        return greeting_text

    async def get_next_step(
        self,
        user_query: str,
        completed_action: str,
        execution_result: str,
        blackboard_artifacts: str = "",
    ) -> Optional[ConciergeProposal]:
        """Evaluates completed tasks and returns a validated Pydantic proposal."""
        if not self.registry.get("abilities", {}).get("proactive_proposals", True):
            return None

        clean_query = user_query.strip().lower().rstrip(".!")

        if clean_query in EXIT_PHRASES:
            logger.debug("Exit phrase detected. Suppressing proposal.")
            return None

        if any(pattern.match(clean_query) for pattern in TRIVIAL_QUERY_PATTERNS):
            logger.debug("Trivial query detected. Suppressing proposal.")
            return None

        # Inject the learned heuristics into the LLM context
        active_rules = self._get_active_heuristics()

        user_content = (
            f"USER QUERY: {user_query}\n"
            f"EXECUTED ACTION: {completed_action}\n"
            f"BLACKBOARD STATE:\n{blackboard_artifacts}\n"
            f"RESULT OUTPUT:\n{execution_result[:1500]}\n"
            f"{active_rules}"
        )
        full_corpus = f"{user_query} {execution_result} {blackboard_artifacts} {active_rules}"

        try:
            response = await self.client.generate(
                model=self.model_name,
                system=CONCIERGE_SYSTEM_PROMPT,
                prompt=user_content,
                format=ConciergeResponse.model_json_schema(),
                options={"temperature": self.temp_proposal},
            )

            if not response or not response.get("response"):
                return None

            response_data = json.loads(response["response"])

            parsed = ConciergeResponse.model_validate(
                response_data,
                context={
                    "user_query": user_query,
                    "full_corpus": full_corpus,
                    "min_confidence": self.min_confidence,
                },
            )

            if not parsed.has_proposal or not parsed.proposal:
                logger.debug("LLM explicitly declined to provide a proposal.")
                return None

            proposal = parsed.proposal
            logger.info(f"Proposal accepted: {proposal.phrase} -> '{proposal.suggested_prompt}'")
            return proposal

        except ValidationError as ve:
            logger.warning(f"Concierge proposal rejected by guardrails: {ve.errors()[0]['msg']}")
            return None
        except Exception as e:
            logger.error(f"Failed to generate dynamic proposal: {e}")
            return None

    async def wrap_payload(self, task_name: str, payload_data: Any) -> str:
        """Intercepts dry system task outputs and translates them into a natural language briefing."""
        try:
            current_context = self.sensor.get_recent_desktop_context(minutes_lookback=2)
        except AttributeError:
            current_context = "Unknown"

        if isinstance(payload_data, (dict, list)):
            try:
                payload_str = json.dumps(payload_data, indent=2)
            except TypeError:
                payload_str = str(payload_data)
        else:
            payload_str = str(payload_data)

        prompt = (
            f"Current User Context: {current_context}\n\n"
            f"Task Executed: {task_name}\n"
            f"Raw Output Data:\n{payload_str}\n\n"
            f"Please provide a natural language summary of this output."
        )

        try:
            logger.debug(f"Wrapping payload for task: {task_name}")
            response = await self.client.generate(
                model=self.model_name,
                system=PAYLOAD_WRAPPER_PROMPT,
                prompt=prompt,
                options={"temperature": self.temp_chat},
            )
            return response.get("response", payload_str).strip('"')

        except Exception as e:
            logger.error(f"Failed to wrap payload for {task_name}: {e}")
            return f"Task '{task_name}' completed. Output: {payload_str}"

    async def handle_user_message(self, user_input: str) -> str:
        """The primary conversational interface for Charon."""
        if self.registry.get("abilities", {}).get("semantic_memory", True):
            # Fire and Forget: Background Memory Extraction
            asyncio.create_task(self.memory.extract_and_store(user_input))

        # Retrieve Context & Memory
        memory_context = self.memory.get_relevant_memories(user_input) if self.chroma_client else ""

        try:
            desktop_context = self.sensor.get_recent_desktop_context(minutes_lookback=5)
        except AttributeError:
            desktop_context = "Unknown"

        dynamic_system_prompt = (
            f"{CONCIERGE_SYSTEM_PROMPT}\n\n"
            f"--- SENSORY DATA ---\n"
            f"Current Desktop Context: {desktop_context}\n"
            f"{memory_context}"
            f"--------------------\n"
        )

        try:
            logger.debug("Generating conversational response with injected memory/context.")
            response = await self.client.generate(
                model=self.model_name,
                system=dynamic_system_prompt,
                prompt=user_input,
                options={"temperature": self.temp_chat},
            )
            return response.get("response", "I seem to have encountered a cognitive error, sir.").strip('"')

        except Exception as e:
            logger.error(f"Failed to generate chat response: {e}")
            return "My apologies, sir, but my communication relays are currently experiencing interference."