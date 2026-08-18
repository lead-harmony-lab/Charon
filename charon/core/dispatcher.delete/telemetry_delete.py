"""
charon/core/dispatcher/telemetry.py
System Version: v0.4.0 | File Revision: 2.1.0

Module: Telemetry dispatch utilities for async streaming to WebSockets and event listeners.
Enforces a strict TelemetryBus Protocol.
"""

import inspect
import logging
from typing import Any, Dict, Protocol, runtime_checkable

import charon.telemetry.trace as trace_module
from charon.telemetry.trace import TraceEvent, TraceEventType

logger = logging.getLogger("Charon.Dispatcher.Telemetry")


@runtime_checkable
class TelemetryBus(Protocol):
    """
    Strict interface for telemetry dispatching.
    Any bus injected into the system MUST implement this protocol.
    """

    async def emit(self, event: Dict[str, Any]) -> None:
        """Dispatches a telemetry event to all connected listeners or sinks."""
        ...


def get_trace_event_type(name: str) -> Any:
    """Safely resolves enum attribute on TraceEventType with dynamic fallbacks."""
    if not name:
        return list(TraceEventType)[0]

    # 1. Exact match
    if hasattr(TraceEventType, name):
        return getattr(TraceEventType, name)

    # 2. Case-insensitive lookup
    upper_name = name.upper()
    if hasattr(TraceEventType, upper_name):
        return getattr(TraceEventType, upper_name)

    for member in TraceEventType:
        if member.name.upper() == upper_name:
            return member

    # 3. Priority fallback strategy
    for fallback in ("STEP", "ACTION", "EXECUTION_STEP", "TASK_STEP", "INITIALIZATION"):
        if hasattr(TraceEventType, fallback):
            return getattr(TraceEventType, fallback)

    return list(TraceEventType)[0]


async def emit_telemetry(event: TraceEvent) -> None:
    """Async dispatch of trace events through a strongly-typed TelemetryBus interface."""
    # Resolve the active bus dynamically from trace module state
    bus = getattr(trace_module, "telemetry_bus", None)
    if bus is None:
        return

    # Enforce the Protocol contract
    if not isinstance(bus, TelemetryBus) and not hasattr(bus, "emit"):
        logger.warning(
            f"Invalid telemetry_bus injected: {type(bus).__name__}. "
            "Must implement the TelemetryBus Protocol (missing 'emit' method)."
        )
        return

    try:
        # Dump event as JSON-compatible dict inside try block to isolate serialization errors
        if hasattr(event, "model_dump"):
            event_dict = event.model_dump(mode="json")
        elif hasattr(event, "dict"):
            event_dict = event.dict()
        else:
            event_dict = event  # type: ignore

        res = bus.emit(event_dict)
        # Forgiving await in case a synchronous testing stub was injected
        if inspect.isawaitable(res):
            await res
    except Exception as err:
        logger.error(f"TelemetryBus emit call failed: {err}", exc_info=True)