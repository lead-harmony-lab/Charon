"""
charon/concierge/core.py
System Version: v3.4.1 | File Revision: 3.8.2

Module: Core Concierge Service
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import chromadb
from charon.config.paths import CONCIERGE_MEMORY_DIR
from charon.concierge.memory import SemanticMemory
from charon.concierge.speech import SpeechEngine
from charon.concierge.telemetry import TelemetrySensor
from charon.concierge.hospitality import HospitalitySubroutine

from charon.gateway.models import WSEvent  # Added for silent text broadcasts

from .autonomic import AutonomicSystem
from .interaction import InteractionEngine
from .observer import ConciergeObserver

logger = logging.getLogger("Charon.UX.Concierge")

DEFAULT_REGISTRY_PATH = Path("charon/config/registry/concierge.json")


class ConciergeService:
    """Central Facade for the Concierge system."""

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

        model_cfg = self.registry.get("model_settings", {})
        self.model_name = model_name or model_cfg.get("model_name", "llama3.1")
        self.min_confidence = (
            min_confidence if min_confidence is not None else model_cfg.get("min_confidence_threshold", 0.7)
        )

        self.sensor = TelemetrySensor()
        self.speech_engine = SpeechEngine()
        self.avatar_service = None  # Will be bound during FastAPI lifespan
        self._init_memory()

        # 1. Initialize Sub-Systems via Composition

        # Initialize without the avatar_service (it gets injected during FastAPI lifespan)
        self.hospitality = HospitalitySubroutine(
            llm_client=self.client,
            memory=self.memory
        )
        self.hospitality.concierge = self  # Give hospitality access to central broadcast

        self.interactions = InteractionEngine(
            client=self.client,
            registry=self.registry,
            memory=self.memory,
            sensor=self.sensor,
            model_name=self.model_name,
            min_confidence=self.min_confidence,
            chroma_client=self.chroma_client,
            memory_collection=self.memory_collection,
            heuristics_collection=self.heuristics_collection,
        )
        self.interactions.concierge = self  # Give interactions access to central broadcast

        self.autonomics = AutonomicSystem(
            registry=self.registry,
            sensor=self.sensor,
            speech_engine=self.speech_engine,
            interaction_engine=self.interactions,
            memory_collection=self.memory_collection,
            hospitality=self.hospitality  # Pass it down to the biological clock
        )

        self.observer = ConciergeObserver(
            sensor=self.sensor,
            memory=self.memory,
            interactions=self.interactions,
            registry=self.registry,
        )

        # Expose public contracts for backwards compatibility & orchestrator pass-through
        self.observe_ingress = self.observer.observe_ingress
        self.observe_egress = self.observer.observe_egress
        self.on_ingress = self.observer.on_ingress
        self.on_egress = self.observer.on_egress
        self.generate_greeting = self.interactions.generate_greeting
        self.get_next_step = self.interactions.get_next_step
        self.wrap_payload = self.interactions.wrap_payload

    def bind_avatar_service(self, avatar_service: Any):
        """Injects the live WebSocket manager into active subsystems."""
        self.avatar_service = avatar_service
        self.hospitality.avatar_service = avatar_service
        # Bind it to the interaction engine so it can push visual states
        self.interactions.avatar_service = avatar_service

    async def broadcast(self, message: str, context: str = "general") -> None:
        """
        Central multimodal emission channel.
        Routes to Text-Only or Text+TTS based on the voice_synthesis registry flag.
        """
        if not self.avatar_service:
            logger.warning(f"Broadcast suppressed: No avatar_service bound. Message was: {message}")
            return

        audio_enabled = self.registry.get("abilities", {}).get("voice_synthesis", False)

        if audio_enabled:
            # Pathway A: Text + TTS Audio + Visemes
            asyncio.create_task(
                self.speech_engine.synthesize_and_broadcast(
                    text=message,
                    avatar_stream=self.avatar_service
                )
            )
        else:
            # Pathway B: Silent Text-Only Broadcast
            event = WSEvent(
                event_type="concierge_suggestion",
                task_id="system",
                agent_name="Concierge",
                data={
                    "suggestion": message,
                    "context": context
                }
            )
            await self.avatar_service.broadcast(event)

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
        """Hot-reloads configuration options from disk and updates sub-systems."""
        self.registry = self._load_registry()
        model_cfg = self.registry.get("model_settings", {})
        self.model_name = model_cfg.get("model_name", self.model_name)
        self.min_confidence = model_cfg.get("min_confidence_threshold", self.min_confidence)

        # Update sub-system parameters
        self.interactions.registry = self.registry
        self.interactions.model_name = self.model_name
        self.interactions.min_confidence = self.min_confidence
        self.interactions.temp_greeting = model_cfg.get("temperature_greeting", self.interactions.temp_greeting)
        self.interactions.temp_proposal = model_cfg.get("temperature_proposal", self.interactions.temp_proposal)
        self.interactions.temp_chat = model_cfg.get("temperature_chat", self.interactions.temp_chat)

        self.autonomics.registry = self.registry
        self.observer.registry = self.registry
        logger.info("Concierge registry parameters successfully reloaded across sub-systems.")

    def _init_memory(self):
        """Initializes ChromaDB and SemanticMemory."""
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

        self.memory = SemanticMemory(
            llm_client=self.client,
            model_name=self.model_name,
            chroma_client=self.chroma_client,
        )

    async def awaken(self):
        """Starts background daemons."""
        await self.autonomics.start()

        abilities = self.registry.get("abilities", {})
        logger.info(f"The Continental is online. Charon is awake. Active abilities: {abilities}")

    async def sleep(self):
        """Gracefully halts background operations."""
        self.autonomics.stop()
        logger.info("Charon has entered standby.")

    async def handle_user_message(self, user_input: str) -> str:
        """Route to interaction engine."""
        return await self.interactions.handle_user_message(user_input)