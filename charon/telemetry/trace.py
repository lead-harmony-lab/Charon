"""
charon/telemetry/trace.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Execution Trace Schemas and Real-Time Event Bus.
Captures agent chain-of-thought reasoning, contract evaluations, step outcomes,
and handoff exceptions in memory without writing noise to persistent database ledgers.
"""

from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    INITIALIZATION = "INITIALIZATION"
    PROBE = "PROBE"
    NEGOTIATION = "NEGOTIATION"
    THINKING = "THINKING"
    COT = "COT"
    PROGRESS = "PROGRESS"
    RESPONSE = "RESPONSE"
    EXECUTION = "EXECUTION"
    EXECUTION_START = "EXECUTION_START"
    EXECUTION_END = "EXECUTION_END"
    HANDOFF = "HANDOFF"
    ESCALATION = "ESCALATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Added Lifecycle & Security Events
    CONTRACT_MINT = "CONTRACT_MINT"
    CONTRACT_BURN = "CONTRACT_BURN"
    JIT_EXPANSION = "JIT_EXPANSION"
    SKILL_CHECKOUT = "SKILL_CHECKOUT"
    CLEANUP = "CLEANUP"


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
    """Ephemeral pub/sub event bus streaming trace events to subscribers."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[TraceEvent], None]] = []
        self._current_trace: Optional[ExecutionTrace] = None

    def emit(self, event: Union[TraceEvent, Dict[str, Any]]) -> None:
        # Auto-coerce raw dictionary inputs into strongly-typed TraceEvent models
        if isinstance(event, dict):
            try:
                raw_type = event.get("event_type", TraceEventType.EXECUTION)
                if isinstance(raw_type, str) and raw_type.upper() in TraceEventType.__members__:
                    event["event_type"] = TraceEventType[raw_type.upper()]
                trace_event = TraceEvent(**event)
            except Exception as parse_err:
                trace_event = TraceEvent(
                    event_type=TraceEventType.EXECUTION,
                    agent_name=str(event.get("agent_name", "System")),
                    action=str(event.get("action", "unknown")),
                    details={"raw_payload": event, "parse_error": str(parse_err)}
                )
        else:
            trace_event = event

        if self._current_trace:
            self._current_trace.events.append(trace_event)
            self._current_trace.active_agent = trace_event.agent_name

        for listener in self._listeners:
            try:
                listener(trace_event)
            except Exception:
                pass

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

    @property
    def current_trace(self) -> Optional[ExecutionTrace]:
        return self._current_trace


# Global Singleton Telemetry Bus
telemetry_bus = TelemetryBus()