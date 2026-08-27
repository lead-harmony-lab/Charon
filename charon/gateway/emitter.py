"""
charon/gateway/emitter.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: WebSocket Event Emitter.
Handles targeted or broadcast WebSocket event transmissions with socket error recovery
and direct support for live ThoughtRecord stream emissions.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from charon.gateway.models import WSEvent
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Emitter")


class EventEmitter:
    """Handles targeted or broadcast WebSocket event transmissions with socket error recovery."""

    def __init__(self):
        self.current_task_id: Optional[str] = None
        self.current_client_id: Optional[str] = None
        self.current_agent: str = "System"

    def set_context(self, task_id: Optional[str], client_id: Optional[str]) -> None:
        """Update active client/task context for targeted transmissions."""
        self.current_task_id = task_id
        self.current_client_id = client_id

    def set_active_agent(self, agent_name: str) -> None:
        """Update the currently active agent for telemetry tracking."""
        self.current_agent = agent_name

    def clear_context(self) -> None:
        """Clear client/task context after execution loop completion."""
        self.current_task_id = None
        self.current_client_id = None
        self.current_agent = "System"

    async def emit_targeted(self, event: WSEvent) -> None:
        """Send event to specific client if bound and connected, with fallback to broadcast on missing/dead sockets."""
        if self.current_client_id and manager.is_client_connected(self.current_client_id):
            try:
                await manager.send_to_client(self.current_client_id, event)
                return
            except Exception as e:
                logger.warning(
                    f"Targeted socket delivery failed for client '{self.current_client_id}': {e}. Fallback to broadcast."
                )

        try:
            await manager.broadcast(event)
        except Exception as e:
            logger.error(f"Failed to broadcast WebSocket event: {e}", exc_info=True)

    async def emit_thought(self, thought_data: Dict[str, Any]) -> None:
        """Emit live CoT thought telemetry event from TaskBlackboard thought stream."""
        agent_name = thought_data.get("source_agent", self.current_agent)
        await self.emit_targeted(
            WSEvent(
                event_type="thought_record",
                task_id=self.current_task_id,
                agent_name=agent_name,
                data=thought_data,
            )
        )

    async def emit_agent_action(
        self,
        agent: str,
        action: str,
        phase: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit real-time sub-step agent action frame to drive CLI spinner status."""
        self.set_active_agent(agent)
        data: Dict[str, Any] = {"agent": agent, "action": action}
        if phase:
            data["phase"] = phase
        if extra_data:
            data.update(extra_data)

        await self.emit_targeted(
            WSEvent(
                event_type="agent_action",
                task_id=self.current_task_id,
                agent_name=agent,
                data=data,
            )
        )

    async def emit_step(self, step_description: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Emit high-level plan step execution event."""
        data: Dict[str, Any] = {"step": step_description}
        if extra_data:
            data.update(extra_data)

        await self.emit_targeted(
            WSEvent(
                event_type="step",
                task_id=self.current_task_id,
                agent_name=self.current_agent,
                data=data,
            )
        )

    async def emit_progress(self, message: str, phase: Optional[str] = None, agent_name: Optional[str] = None) -> None:
        """Emit general progress update message."""
        active_agent = agent_name or self.current_agent
        data: Dict[str, Any] = {"message": message}
        if phase:
            data["phase"] = phase

        await self.emit_targeted(
            WSEvent(
                event_type="task_progress",
                task_id=self.current_task_id,
                agent_name=active_agent,
                data=data,
            )
        )

    async def emit_stream(self, message: str, agent_name: Optional[str] = None) -> None:
        """Emit agent log/stream output globally so monitors can render it."""
        active_agent = agent_name or self.current_agent
        event = WSEvent(
            event_type="agent_log",
            task_id=self.current_task_id,
            agent_name=active_agent,
            data={"message": message},
        )
        try:
            await manager.broadcast(event)
        except Exception as e:
            logger.error(f"Failed to broadcast stream token: {e}")

    async def emit_completed(self, message: str, agent_name: Optional[str] = None) -> None:
        """Emit task completion event."""
        active_agent = agent_name or self.current_agent
        await self.emit_targeted(
            WSEvent(
                event_type="task_complete",
                task_id=self.current_task_id,
                agent_name=active_agent,
                data={
                    "summary": message,
                    "result": message,
                    "output": message,
                    "content": message,
                },
            )
        )

    async def emit_error(self, error_message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emit task failure/error event for UI alert rendering."""
        data: Dict[str, Any] = {"error": error_message}
        if details:
            data["details"] = details

        await self.emit_targeted(
            WSEvent(
                event_type="task_error",
                task_id=self.current_task_id,
                agent_name="System",
                data=data,
            )
        )

    async def emit_gatekeeper(
        self, manifest_message: str, action: str, approval_id: Optional[str] = None
    ) -> str:
        """
        Emit gatekeeper intercept request using the bound approval token ID.
        Returns the active approval ID.
        """
        token = approval_id or f"appr_{uuid.uuid4().hex[:8]}"
        await self.emit_targeted(
            WSEvent(
                event_type="gatekeeper_intercept",
                task_id=self.current_task_id,
                agent_name="Gatekeeper",
                data={
                    "manifest": manifest_message,
                    "action": action,
                    "approval_id": token,
                },
            )
        )
        return token

    async def emit_agent_response(self, agent: str, content: str) -> None:
        """Emit completed agent output response."""
        await self.emit_targeted(
            WSEvent(
                event_type="agent_response",
                task_id=self.current_task_id,
                agent_name=agent,
                data={"agent": agent, "content": content},
            )
        )

    async def emit_telemetry_trace(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emit routing and execution telemetry for HUD visualizers."""
        data = {"event_type": event_type}
        if details:
            data["details"] = details
            if "action" in details:
                data["action"] = details["action"]

        await self.emit_targeted(
            WSEvent(
                event_type="telemetry_trace",
                task_id=self.current_task_id,
                agent_name=self.current_agent,
                data=data,
            )
        )

    async def emit_system_event(self, payload: Dict[str, Any]) -> None:
        """Emit system-level events (like TaskDispatched) to acknowledge ingestion and prevent timeouts."""
        event_type = payload.get("event_type", "system_event")
        await self.emit_targeted(
            WSEvent(
                event_type=event_type,
                task_id=self.current_task_id or payload.get("task_id"),
                agent_name="System",
                data=payload,
            )
        )