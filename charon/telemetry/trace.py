"""
charon/telemetry/trace.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Execution Trace Schemas and Real-Time Event Bus.
Captures agent chain-of-thought reasoning, contract evaluations, step outcomes,
and handoff exceptions in memory without writing noise to persistent database ledgers.
"""

from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    INITIALIZATION = "INITIALIZATION"
    PROBE = "PROBE"
    NEGOTIATION = "NEGOTIATION"
    THINKING = "THINKING"
    EXECUTION = "EXECUTION"
    EXECUTION_START = "EXECUTION_START"
    EXECUTION_END = "EXECUTION_END"
    HANDOFF = "HANDOFF"
    ESCALATION = "ESCALATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TraceEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    event_type: TraceEventType
    agent_name: str
    action: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    reasoning_chunk: Optional[str] = None
    duration_ms: Optional[float] = None


class ExecutionTrace(BaseModel):
    trace_id: str
    original_prompt: str
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    events: List[TraceEvent] = Field(default_factory=list)
    active_agent: str = "Coordinator"
    status: str = "IN_PROGRESS"


class TelemetryBus:
    """Ephemeral pub/sub event bus streaming trace events to subscribers (e.g., CLI viewer)."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[TraceEvent], None]] = []
        self._current_trace: Optional[ExecutionTrace] = None

    def start_trace(self, trace_id: str, prompt: str) -> ExecutionTrace:
        self._current_trace = ExecutionTrace(trace_id=trace_id, original_prompt=prompt)
        self.emit(
            TraceEvent(
                event_type=TraceEventType.INITIALIZATION,
                agent_name="Coordinator",
                details={"prompt": prompt},
            )
        )
        return self._current_trace

    def subscribe(self, listener: Callable[[TraceEvent], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[TraceEvent], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(self, event: TraceEvent) -> None:
        if self._current_trace:
            self._current_trace.events.append(event)
            self._current_trace.active_agent = event.agent_name

        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

    @property
    def current_trace(self) -> Optional[ExecutionTrace]:
        return self._current_trace


# Global Singleton Telemetry Bus
telemetry_bus = TelemetryBus()
