"""
charon/concierge/core.py
System Version: v3.6.5

Module: Core Concierge Service
"""
import asyncio
import datetime
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
from charon.concierge.schemas import CharonSignal, Modality
from charon.gateway.models import WSEvent

from .autonomic import AutonomicSystem
from .interaction import InteractionEngine
from .observer import ConciergeObserver

logger = logging.getLogger("Charon.UX.Concierge")

DEFAULT_REGISTRY_PATH = Path("charon/config/registry/concierge.json")


class MultimodalRouter:
    """Routes concierge signals to specific UI clients based on modality."""

    # Notice we keep all clients in the matrix for native delivery
    ROUTING_MATRIX = {
        Modality.PROCESS: ["cli_terminal", "react_dashboard"],
        Modality.THOUGHT: ["gtk4_avatar", "react_dashboard"],
        Modality.DIALOGUE: ["gtk4_avatar", "react_dashboard"]
    }

    @classmethod
    async def dispatch(cls, signal: CharonSignal, ws_manager: Any):
        if not ws_manager:
            return

        # -------------------------------------------------------------
        # LANE A: The GNOME Shell "Smuggling Vector" (Broadcast)
        # -------------------------------------------------------------
        if signal.modality == Modality.PROCESS:
            metadata = signal.metadata or {}
            ws_event = WSEvent.model_construct(
                event_type=metadata.get("event_type", "status_change"),
                agent_name="Concierge",
                client_id="desktop_concierge",
                data={
                    "status": metadata.get("status", "active"),
                    "message": signal.content,
                }
            )
            try:
                # FIX: Serialize the Pydantic model to a dict before broadcasting to prevent malformed JSON strings
                payload = ws_event.model_dump() if hasattr(ws_event, "model_dump") else ws_event.dict()
                await ws_manager.broadcast(payload)
            except Exception as e:
                logger.error(f"[Router] Failed to broadcast PROCESS signal to GNOME: {e}")

        # -------------------------------------------------------------
        # LANE B: Native Point-to-Point Routing (Avatar, Dashboard, CLI)
        # -------------------------------------------------------------
        # The hospitality sequence and avatar depend on direct send_to_client delivery.
        target_clients = cls.ROUTING_MATRIX.get(signal.modality, [])

        if not target_clients:
            return

        # Serialize standard CharonSignal payload once
        if hasattr(signal, "model_dump_json"):
            base_payload = json.loads(signal.model_dump_json())
        elif hasattr(signal, "json"):
            base_payload = json.loads(signal.json())
        else:
            base_payload = signal.dict()

        for client_id in target_clients:
            if ws_manager.is_client_connected(client_id):
                try:
                    await ws_manager.send_to_client(client_id, base_payload)
                except Exception as e:
                    logger.error(f"[Router] Failed to send {signal.modality.value} to {client_id}: {e}")


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
        self.ws_manager = None  # Will be bound during FastAPI lifespan
        self._init_memory()

        # 1. Initialize Sub-Systems via Composition
        self.hospitality = HospitalitySubroutine(
            llm_client=self.client,
            sensor=self.sensor,
            broadcast_callback=self.broadcast,
            process_callback=self.emit_process,
            model_name=self.model_name,
            memory=self.memory
        )

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
            broadcast_callback=self.broadcast
        )

        self.autonomics = AutonomicSystem(
            registry=self.registry,
            sensor=self.sensor,
            speech_engine=self.speech_engine,
            interaction_engine=self.interactions,
            memory_collection=self.memory_collection,
            hospitality=self.hospitality,
            broadcast_callback=self.broadcast,
            process_callback=self.emit_process
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
        self.classify_intent = self.interactions.classify_intent
        self.handle_conversational_bypass = self.interactions.handle_conversational_bypass

    def bind_ws_manager(self, manager: Any):
        """Injects the unified live WebSocket manager into active subsystems."""
        self.ws_manager = manager
        self.hospitality.ws_manager = manager
        self.interactions.ws_manager = manager
        self.observer.ws_manager = manager
        self.autonomics.ws_manager = manager

    async def handle_client_payload(self, client_id: str, payload: dict) -> None:
        """
        Ingress hook for incoming WebSocket payloads from UI clients.
        Routes HIL (Human-in-the-Loop) authorization responses and other direct client signals.
        """
        event_type = payload.get("event_type") or payload.get("action")

        if event_type == "hil_auth_response":
            task_id = payload.get("task_id")
            granted = payload.get("granted", False)

            if not task_id:
                logger.warning(f"[{client_id}] Malformed HIL response received: Missing task_id.")
                return

            logger.info(f"[Concierge] HIL authorization reply received for task {task_id}: {granted}")
            # Unblock the suspended interaction engine thread
            self.interactions.resolve_hil_authorization(task_id, granted)

        elif event_type == "user_message":
            user_text = payload.get("text", "")
            # Example routing for standard text inputs from the UI
            if user_text:
                asyncio.create_task(self.handle_user_message(user_text))

        else:
            logger.debug(f"[Concierge] Unhandled ingress payload from {client_id}: {payload}")

    async def broadcast(
        self,
        message: str,
        context: str = "general",
        modality: Optional[Modality] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Central multimodal emission channel.
        Routes to Text-Only or Text+TTS based on the voice_synthesis registry flag.
        """
        if not self.ws_manager:
            logger.warning(f"Broadcast suppressed: No ws_manager bound. Message was: {message}")
            return

        # Default to Dialogue if not explicitly passed
        active_modality = modality or Modality.DIALOGUE
        audio_enabled = self.registry.get("abilities", {}).get("voice_synthesis", False)

        # Merge caller-provided metadata with defaults
        signal_metadata = {
            "avatar_state": {"emotion": "speaking"},
            "urgency": "medium"
        }
        if metadata:
            signal_metadata.update(metadata)

        # 1. ALWAYS dispatch the visual/text payload to UI clients
        try:
            signal = CharonSignal(
                modality=active_modality,
                content=message,
                context=context,
                timestamp=datetime.datetime.now().isoformat(),
                metadata=signal_metadata
            )
            await MultimodalRouter.dispatch(signal, self.ws_manager)
        except Exception as e:
            logger.error(f"[Concierge] Failed to route broadcast signal: {e}")

        # 2. CONCURRENTLY dispatch audio synthesis if enabled
        if audio_enabled:
            asyncio.create_task(
                self.speech_engine.synthesize_and_broadcast(
                    text=message,
                    ws_manager=self.ws_manager
                )
            )

    async def trigger_hospitality(self, client_id: str) -> None:
        """
        Facade method to trigger the autonomic hospitality sequence.
        Routes the client_ready event down to the appropriate subroutine.
        """
        logger.info(f"[Concierge] Delegating hospitality sequence for client '{client_id}'")

        # Trigger Hospitality independently
        if hasattr(self.hospitality, "trigger_hospitality"):
            await self.hospitality.trigger_hospitality(client_id=client_id)
        else:
            logger.warning("[Concierge] 'trigger_hospitality' not found in HospitalitySubroutine.")

        # Trigger Autonomics independently (No longer shadowed by an 'elif')
        if hasattr(self.autonomics, "trigger_hospitality"):
            await self.autonomics.trigger_hospitality(client_id=client_id)
        else:
            logger.warning("[Concierge] 'trigger_hospitality' not found in AutonomicSystem.")

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

        if self.chroma_client:
            self.memory = SemanticMemory(
                llm_client=self.client,
                model_name=self.model_name,
                chroma_client=self.chroma_client,
            )
        else:
            self.memory = None
            logger.warning("[Core] Operating in amnesiac mode: SemanticMemory is disabled.")

    async def handle_user_message(self, user_input: str) -> str:
        """Route to interaction engine."""
        return await self.interactions.handle_user_message(user_input)

    async def emit_process(self, message: str, context: str = "system", status: str = "active") -> None:
        """
        Dedicated channel for non-verbal, systemic process events.
        Targeted at UI clients requiring state/status updates (e.g., GNOME shell, CLI).
        """
        if not self.ws_manager:
            return

        try:
            signal = CharonSignal(
                modality=Modality.PROCESS,
                content=message,
                context=context,
                timestamp=datetime.datetime.now().isoformat(),
                metadata={
                    "event_type": "agent_status",  # Changed from "status_change" to route correctly in GNOME UI
                    "status": status,
                    "urgency": "low"
                }
            )
            await MultimodalRouter.dispatch(signal, self.ws_manager)
        except Exception as e:
            logger.error(f"[Concierge] Failed to emit process signal: {e}")

    async def awaken(self):
        """Starts background daemons and notifies UI clients."""
        await self.autonomics.start()

        abilities = self.registry.get("abilities", {})
        logger.info(f"The Continental is online. Charon is awake. Active abilities: {abilities}")

        # Broadcast visual system readiness
        await self.emit_process("Concierge subsystems online.", context="lifecycle", status="ready")

    async def sleep(self):
        """Gracefully halts background operations."""
        self.autonomics.stop()
        logger.info("Charon has entered standby.")

        # Broadcast visual shutdown
        await self.emit_process("Concierge entering standby.", context="lifecycle", status="inactive")

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
        self.interactions.temp_greeting = model_cfg.get("temperature_greeting",
                                                        getattr(self.interactions, "temp_greeting", 0.7))
        self.interactions.temp_proposal = model_cfg.get("temperature_proposal",
                                                        getattr(self.interactions, "temp_proposal", 0.7))
        self.interactions.temp_chat = model_cfg.get("temperature_chat", getattr(self.interactions, "temp_chat", 0.7))

        self.autonomics.registry = self.registry
        self.observer.registry = self.registry

        logger.info("Concierge registry parameters successfully reloaded across sub-systems.")

        # Fire-and-forget the process event since this is a sync method
        if self.ws_manager:
            asyncio.create_task(
                self.emit_process("Registry parameters hot-reloaded.", context="config", status="active")
            )

    async def request_hil_authorization(self, task_id: str, intent_summary: str) -> bool:
        """
        Proxy method to request Human-in-the-Loop authorization.
        Delegates to the InteractionEngine which handles broadcasting and thread suspension.
        """
        logger.info(f"[Concierge] Proxying HIL authorization request for task: {task_id}")

        # Directly await the InteractionEngine, which manages the asyncio.Event lock internally
        return await self.interactions.request_hil_authorization(task_id, intent_summary)