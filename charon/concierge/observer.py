"""
charon/concierge/observer.py
System Version: v3.4.1 | File Revision: 3.5.0

Handles Ingress/Egress hooks for the Orchestration Engine, managing telemetry
injection, state tracking, and UI emission decoupling.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from .telemetry import HarnessState

logger = logging.getLogger("Charon.UX.Concierge.Observer")


class ConciergeObserver:
    """Pass-through observer for the core orchestration execution loop."""

    def __init__(
        self,
        sensor: Any,
        memory: Any,
        interactions: Any,
        registry: Dict[str, Any]
    ):
        self.sensor = sensor
        self.memory = memory
        self.interactions = interactions
        self.registry = registry

    # =========================================================================
    # Window & Sensory Ingress Event Handlers
    # =========================================================================

    def record_window_context(
        self,
        app_name: str,
        window_title: str,
        active_file_path: Optional[str] = None,
        pid: Optional[int] = None,
        workspace: int = 0
    ) -> None:
        """
        Ingests active desktop window focus events, logs telemetry into sensor cache,
        and updates active working memory state for immediate engine reference.
        """
        if hasattr(self.sensor, "log_window_context"):
            self.sensor.log_window_context(
                app_name=app_name,
                window_title=window_title,
                active_file_path=active_file_path,
                pid=pid,
                workspace=workspace
            )

        if hasattr(self.memory, "set_working_context"):
            self.memory.set_working_context("active_window", {
                "app_name": app_name,
                "window_title": window_title,
                "active_file_path": active_file_path or ""
            })

        logger.debug(f"[Observer.Window] Ingested active window context: {app_name} | {window_title}")

    # =========================================================================
    # Observer Pipeline Hooks (Engine Pass-Through)
    # =========================================================================

    async def observe_ingress(
        self,
        task_id: Optional[str],
        prompt: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Pre-flight hook for the Orchestration Engine.
        Injects structured active window and desktop context into task metadata.
        """
        safe_task_id = task_id or "volatile"
        logger.debug(f"[Observer.Ingress] Observing ingress for task: {safe_task_id}")

        # 1. Fetch live cached window state and semantic history vector context
        try:
            active_window = getattr(self.sensor, "get_active_window_context", lambda: None)()
            desktop_context = self.sensor.get_recent_desktop_context(minutes_lookback=2)
        except Exception as e:
            logger.warning(f"[Observer.Ingress] Failed to retrieve desktop context: {e}")
            active_window = None
            desktop_context = "Unknown"

        # 2. Inject context into metadata for downstream agents & InteractionEngine
        if "system_context" not in metadata:
            metadata["system_context"] = {}

        metadata["system_context"]["desktop_activity"] = desktop_context
        metadata["system_context"]["active_window"] = active_window or {}

        # 3. Trigger standard ingress lifecycle (state tracking, memory)
        await self.on_ingress(user_prompt=prompt, task_id=safe_task_id)

        return prompt, metadata

    async def observe_egress(
        self,
        task_id: Optional[str],
        user_query: str,
        execution_result: str,
        blackboard_artifacts: str,
        emitter: Any
    ) -> None:
        """
        Post-flight hook for the Orchestration Engine.
        Evaluates results, generates UX proposals, and emits to the WebSocket.
        """
        safe_task_id = task_id or "volatile"
        logger.debug(f"[Observer.Egress] Observing egress for task: {safe_task_id}")

        # 1. Trigger standard egress lifecycle (summary, proposal generation, state reset)
        egress_data = await self.on_egress(
            task_id=safe_task_id,
            user_prompt=user_query,
            completed_action="engine_execution",
            execution_result=execution_result,
            blackboard_artifacts=blackboard_artifacts,
            is_error="error" in execution_result.lower() if isinstance(execution_result, str) else False
        )

        # 2. Native Output Broadcast via UI Emitter
        if emitter and hasattr(emitter, "emit"):
            try:
                payload = {
                    "task_id": safe_task_id,
                    "summary": egress_data.get("summary"),
                    "proposal": egress_data.get("proposal")
                }
                # Pushes the evaluated next-step UX directly to the frontend
                await emitter.emit(event="task_completed", data=payload)
                logger.info(f"[Observer.Egress] Successfully emitted UX payload for task {safe_task_id}")
            except Exception as e:
                logger.error(f"[Observer.Egress] Failed to emit egress UX payload: {e}")

    # =========================================================================
    # Internal Lifecycle Hooks
    # =========================================================================

    async def on_ingress(self, user_prompt: str, task_id: str) -> None:
        """Handles internal state shifts and memory extraction upon prompt arrival."""
        logger.info(f"[Observer.Lifecycle] Intercepted prompt for Task {task_id}: '{user_prompt[:60]}...'")

        # 1. Transition Harness State to RUNNING
        self.sensor.set_harness_state(
            state=HarnessState.RUNNING,
            task_id=task_id,
            prompt=user_prompt
        )

        # 2. Extract & Store Semantic Memory (Fire & Forget in background)
        if self.registry.get("abilities", {}).get("semantic_memory", True):
            asyncio.create_task(self.memory.extract_and_store(user_prompt))

    async def on_egress(
        self,
        task_id: str,
        user_prompt: str,
        completed_action: str,
        execution_result: str,
        blackboard_artifacts: str = "",
        is_error: bool = False
    ) -> Dict[str, Any]:
        """Handles post-execution evaluation, natural language wrapping, and state reset."""
        logger.info(f"[Observer.Lifecycle] Processing execution output for Task {task_id}")

        # 1. Update Harness State based on success/error
        new_state = HarnessState.FAULTED if is_error else HarnessState.IDLE
        self.sensor.set_harness_state(state=new_state, task_id=task_id)

        # 2. Wrap Payload into Natural Language Summary (Delegated to InteractionEngine)
        wrapped_summary = await self.interactions.wrap_payload(
            task_name=completed_action,
            payload_data=execution_result
        )

        # 3. Evaluate Proactive Proposal (Delegated to InteractionEngine)
        proposal = await self.interactions.get_next_step(
            user_query=user_prompt,
            completed_action=completed_action,
            execution_result=execution_result,
            blackboard_artifacts=blackboard_artifacts
        )

        # 4. Final Reset of Harness State back to IDLE
        self.sensor.set_harness_state(state=HarnessState.IDLE)

        return {
            "task_id": task_id,
            "summary": wrapped_summary,
            "proposal": proposal.model_dump() if proposal else None
        }