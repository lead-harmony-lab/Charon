"""
charon/concierge/interaction.py
System Version: v3.5.1

Handles all direct LLM generation tasks including conversational chat,
payload wrapping, proactive proposals, and dynamic greetings.
"""
import asyncio
import datetime
import json
import logging
from typing import Any, Dict, Optional

from pydantic import ValidationError

from .constants import EXIT_PHRASES, TRIVIAL_QUERY_PATTERNS
from .prompts import (
    CONCIERGE_SYSTEM_PROMPT,
    GREETING_SYSTEM_PROMPT,
    PAYLOAD_WRAPPER_PROMPT,
)
from .schemas import ConciergeProposal, ConciergeResponse, Modality

logger = logging.getLogger("Charon.UX.Concierge.Interaction")


class InteractionEngine:
    """Isolates and manages all generative AI interactions for the Concierge."""

    def __init__(
        self,
        client: Any,
        registry: Dict[str, Any],
        memory: Optional[Any],
        sensor: Any,
        model_name: str,
        min_confidence: float,
        chroma_client: Optional[Any] = None,
        memory_collection: Optional[Any] = None,
        heuristics_collection: Optional[Any] = None,
        broadcast_callback: Optional[Any] = None,
    ):
        self.client = client
        self.registry = registry
        self.memory = memory
        self.sensor = sensor
        self.model_name = model_name
        self.min_confidence = min_confidence
        self.chroma_client = chroma_client
        self.memory_collection = memory_collection
        self.heuristics_collection = heuristics_collection
        self.broadcast = broadcast_callback

        # Extract generation configurations
        model_cfg = self.registry.get("model_settings", {})
        self.temp_greeting = model_cfg.get("temperature_greeting", 0.6)
        self.temp_proposal = model_cfg.get("temperature_proposal", 0.2)
        self.temp_chat = model_cfg.get("temperature_chat", 0.7)

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
            logger.debug(f"[Interaction] Failed to fetch heuristics: {e}")
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
                logger.debug(f"[Interaction] Could not fetch concierge memory, defaulting to cold start: {e}")

        last_time = datetime.datetime.fromisoformat(last_briefing_doc["timestamp"])
        hours_since_last = (now - last_time).total_seconds() / 3600.0

        # 2. Query the TelemetrySensor for actual session deltas
        try:
            deltas = await self.sensor.get_session_deltas(last_briefing_doc["timestamp"])
            current_task_count = deltas.get("task_count", 0)
            current_alert_count = deltas.get("alert_count", 0)
        except Exception as e:
            logger.error(f"[Interaction] Failed to fetch session deltas from ledger: {e}")
            current_task_count = 0
            current_alert_count = 0

        # 3. Determine Briefing Context based on actual deltas
        has_new_tasks = current_task_count > 0
        has_new_alerts = current_alert_count > 0

        if hours_since_last < warmth_hours and not (has_new_tasks or has_new_alerts):
            logger.debug(f"[Interaction] Briefing bypassed. Session is warm (< {warmth_hours}h) with no state delta.")
            context_str = "Context: [Continuation] | Active Session | No new events"
            should_update_memory = False

        elif hours_since_last < warmth_hours and has_new_alerts:
            logger.debug("[Interaction] Session warm, but new alerts detected. Triggering targeted notification.")
            context_str = f"Context: [Continuation] | Active Session | {current_alert_count} New Alert(s)"
            should_update_memory = True

        else:
            logger.debug("[Interaction] Triggering full system briefing.")
            context_str = (
                f"Context: [Full Briefing] | "
                f"{current_task_count} New Task(s) | {current_alert_count} New Alert(s)"
            )
            should_update_memory = True

        # 4. Generate Persona Greeting
        prompt = f"{context_str}\nGenerate greeting:"
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": GREETING_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temp_greeting,
            )
            greeting_text = response.choices[0].message.content.strip('"')
        except Exception as e:
            logger.error(f"[Interaction] Failed to generate greeting: {e}")
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
                logger.error(f"[Interaction] Failed to save concierge memory state: {e}")

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
            logger.debug("[Interaction] Exit phrase detected. Suppressing proposal.")
            return None

        if any(pattern.match(clean_query) for pattern in TRIVIAL_QUERY_PATTERNS):
            logger.debug("[Interaction] Trivial query detected. Suppressing proposal.")
            return None

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
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": CONCIERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=self.temp_proposal,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "concierge_proposal",
                        "schema": ConciergeResponse.model_json_schema(),
                    },
                },
            )

            if not response or not response.choices:
                return None

            response_data = json.loads(response.choices[0].message.content)

            parsed = ConciergeResponse.model_validate(
                response_data,
                context={
                    "user_query": user_query,
                    "full_corpus": full_corpus,
                    "min_confidence": self.min_confidence,
                },
            )

            if not parsed.has_proposal or not parsed.proposal:
                logger.debug("[Interaction] LLM explicitly declined to provide a proposal.")
                return None

            proposal = parsed.proposal
            logger.info(f"[Interaction] Proposal accepted: {proposal.phrase} -> '{proposal.suggested_prompt}'")
            return proposal

        except ValidationError as ve:
            logger.warning(f"[Interaction] Proposal rejected by guardrails: {ve.errors()[0]['msg']}")
            return None
        except Exception as e:
            logger.error(f"[Interaction] Failed to generate dynamic proposal: {e}")
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
            logger.debug(f"[Interaction] Wrapping payload for task: {task_name}")
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PAYLOAD_WRAPPER_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temp_chat,
            )
            return response.choices[0].message.content.strip('"')

        except Exception as e:
            logger.error(f"[Interaction] Failed to wrap payload for {task_name}: {e}")
            return f"Task '{task_name}' completed. Output: {payload_str}"

    async def handle_user_message(self, user_input: str) -> str:
        """The primary conversational interface for Charon."""

        # 1. EMIT PROCESS SIGNAL (Active)
        if self.broadcast:
            active_metadata = {"event_type": "agent_status", "status": "active"}
            process_msg = "Processing query..."

            if asyncio.iscoroutinefunction(self.broadcast):
                await self.broadcast(process_msg, context="chat_generation", modality=Modality.PROCESS,
                                     metadata=active_metadata)
            else:
                self.broadcast(process_msg, context="chat_generation", modality=Modality.PROCESS,
                               metadata=active_metadata)

        memory_context = ""
        # Safe memory check to prevent amnesiac mode crashes
        if self.memory and hasattr(self.memory, 'get_relevant_memories'):
            memory_context = self.memory.get_relevant_memories(user_input)

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
            logger.debug("[Interaction] Generating conversational response with injected memory/context.")
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": dynamic_system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=self.temp_chat,
            )

            response_text = response.choices[0].message.content.strip('"')

            # 2. EMIT DIALOGUE SIGNAL (Feeds GTK4 Avatar Lane B)
            if self.broadcast:
                if asyncio.iscoroutinefunction(self.broadcast):
                    await self.broadcast(response_text, context="chat_reply", modality=Modality.DIALOGUE)
                else:
                    self.broadcast(response_text, context="chat_reply", modality=Modality.DIALOGUE)

            # 3. RESET PROCESS SIGNAL (Clears GNOME Top-Bar)
            if self.broadcast:
                ready_metadata = {"event_type": "agent_status", "status": "ready"}
                if asyncio.iscoroutinefunction(self.broadcast):
                    await self.broadcast("Ready", context="idle", modality=Modality.PROCESS, metadata=ready_metadata)
                else:
                    self.broadcast("Ready", context="idle", modality=Modality.PROCESS, metadata=ready_metadata)

            return response_text

        except Exception as e:
            logger.error(f"[Interaction] Failed to generate chat response: {e}")

            # RESET ON FAILURE
            if self.broadcast:
                error_metadata = {"event_type": "agent_status", "status": "ready"}
                if asyncio.iscoroutinefunction(self.broadcast):
                    await self.broadcast("Ready", context="error", modality=Modality.PROCESS, metadata=error_metadata)
                else:
                    self.broadcast("Ready", context="error", modality=Modality.PROCESS, metadata=error_metadata)

            return "My apologies, sir, but my communication relays are currently experiencing interference."

    async def classify_intent(self, prompt: str, context: dict) -> str:
        """
        Fast semantic classification to determine if the prompt requires the heavy execution engine.
        """
        logger.debug(f"[Interaction.Router] Classifying intent for prompt: '{prompt[:40]}...'")

        system_rules = (
            "You are a strict routing gateway. Read the user prompt and desktop context. "
            "If the user asks a general question, requests a text summary, or makes casual conversation, output EXACTLY the word 'chat'. "
            "If the user explicitly asks to modify the system, write a script, control hardware, or execute a multi-step workflow, output EXACTLY the word 'agentic'. "
            "Do not output any other text."
        )

        active_window = context.get("active_window", "Unknown")
        desktop_activity = context.get("desktop_activity", "None")
        user_payload = f"Active Window: {active_window}\nRecent Activity: {desktop_activity}\nPrompt: {prompt}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_rules},
                    {"role": "user", "content": user_payload},
                ],
                max_tokens=5,
                temperature=0.1,
            )
            clean_response = response.choices[0].message.content.strip().lower()
            return "chat" if "chat" in clean_response else "agentic"

        except Exception as e:
            logger.error(f"[Interaction.Router] Classification failed, defaulting to agentic: {e}")
            return "agentic"

    async def handle_conversational_bypass(self, prompt: str, context: dict) -> Dict[str, Any]:
        """
        Processes non-agentic prompts directly, maintaining full desktop awareness
        without invoking the Coordinator execution loop.
        """
        logger.info("[Interaction.Bypass] Executing direct conversational response.")

        # 1. EMIT PROCESS SIGNAL (Bypass Mode)
        if self.broadcast:
            active_metadata = {"event_type": "agent_status", "status": "active"}
            process_msg = "Bypassing Engine (Chat Mode)..."
            if asyncio.iscoroutinefunction(self.broadcast):
                await self.broadcast(process_msg, context="chat_generation", modality=Modality.PROCESS,
                                     metadata=active_metadata)
            else:
                self.broadcast(process_msg, context="chat_generation", modality=Modality.PROCESS,
                               metadata=active_metadata)

        system_prompt = (
            "You are Charon, a highly capable, polite, and adaptive AI Concierge. "
            "Your role here is to directly and concisely answer the user's conversational query, "
            "provide requested facts, or engage in pleasant dialogue. Do NOT propose background tasks."
        )

        active_window = context.get("active_window", "Unknown")
        desktop_activity = context.get("desktop_activity", "None")
        enriched_prompt = f"Active Window: {active_window}\nRecent Activity: {desktop_activity}\n\nUser: {prompt}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": enriched_prompt},
                ],
                temperature=self.temp_chat,
            )

            chat_message = response.choices[0].message.content.strip('"').strip()

            # 2. EMIT DIALOGUE SIGNAL (Feeds GTK4 Avatar)
            if self.broadcast:
                if asyncio.iscoroutinefunction(self.broadcast):
                    await self.broadcast(chat_message, context="chat_reply", modality=Modality.DIALOGUE)
                else:
                    self.broadcast(chat_message, context="chat_reply", modality=Modality.DIALOGUE)

            # 3. RESET PROCESS SIGNAL
            if self.broadcast:
                ready_metadata = {"event_type": "agent_status", "status": "ready"}
                if asyncio.iscoroutinefunction(self.broadcast):
                    await self.broadcast("Ready", context="idle", modality=Modality.PROCESS,
                                         metadata=ready_metadata)
                else:
                    self.broadcast("Ready", context="idle", modality=Modality.PROCESS, metadata=ready_metadata)

            return {
                "result": chat_message,
                "type": "chat_bypass"
            }

        except Exception as e:
            logger.error(f"[Interaction.Bypass] Conversational generation failed: {e}")
            return {
                "result": "My apologies, sir, but my bypass relays are experiencing interference.",
                "type": "chat_bypass"
            }

    async def request_hil_authorization(self, task_id: str, intent_summary: str) -> bool:
        """
        Halts the execution thread and emits a WebSocket payload via broadcast.
        Awaits user confirmation via an asynchronous event gate.
        """
        logger.info(f"[Interaction.HIL] Suspending task {task_id} for Gatekeeper authorization.")

        if not hasattr(self, "_pending_auths"):
            self._pending_auths = {}

        auth_event = asyncio.Event()
        self._pending_auths[task_id] = {
            "event": auth_event,
            "granted": False
        }

        # Emit the UI payload to Mutter/GNOME Shell using existing broadcast pipeline
        if self.broadcast:
            hil_metadata = {
                "event_type": "gatekeeper_request",  # Matches ui.js router
                "approval_id": task_id,              # Matches payload extraction
                "action": intent_summary,            # Matches payload extraction
                "avatar_state": "inquiring"
            }
            msg = "Awaiting authorization..."

            if asyncio.iscoroutinefunction(self.broadcast):
                await self.broadcast(msg, context="hil_gatekeeper", modality=Modality.PROCESS,
                                     metadata=hil_metadata)
            else:
                self.broadcast(msg, context="hil_gatekeeper", modality=Modality.PROCESS, metadata=hil_metadata)
        else:
            logger.error("[Interaction.HIL] No broadcast callback bound. Cannot request HIL auth.")
            del self._pending_auths[task_id]
            return False

        # Yield execution until the listener triggers the event
        logger.debug(f"[Interaction.HIL] Task {task_id} sleeping, awaiting HIL socket response...")
        await auth_event.wait()

        # Extract result and cleanup
        granted = self._pending_auths[task_id]["granted"]
        del self._pending_auths[task_id]

        logger.info(f"[Interaction.HIL] Task {task_id} waking up. Authorization granted: {granted}")
        return granted

    def resolve_hil_authorization(self, approval_id: str, decision: Any):
        """
        Sync method called by the WebSocket ingress handler when the GNOME UI replies.
        Unblocks the suspended request_hil_authorization coroutine.
        """
        # Parse standard string responses from ui.js or fallback to boolean
        if isinstance(decision, str):
            granted = decision.lower() in ("proceed", "approve", "allow", "yes", "true")
        else:
            granted = bool(decision)

        if hasattr(self, "_pending_auths") and approval_id in self._pending_auths:
            self._pending_auths[approval_id]["granted"] = granted
            self._pending_auths[approval_id]["event"].set()
        else:
            logger.warning(f"[Interaction.HIL] Received auth for unknown or expired task: {approval_id}")