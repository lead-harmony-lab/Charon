"""
System Version: v1.0.0 | Refactored Work Contract Architecture

Module: Telemetry dispatch utilities for strongly-typed event streaming.
Enforces the TelemetryBus Protocol for dependency injection.
"""

import inspect
import logging
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from charon.telemetry.trace import TraceEvent, TraceEventType

logger = logging.getLogger("Charon.Telemetry")


@runtime_checkable
class TelemetryBus(Protocol):
    """
    Strict interface for telemetry dispatching.
    Any bus injected into the system MUST implement this protocol.
    """

    async def emit(self, event: Dict[str, Any]) -> None:
        """Dispatches a telemetry event to all connected listeners or sinks."""
        ...


def resolve_trace_event_type(event_type: Any) -> TraceEventType:
    """
    Ensures input is a valid TraceEventType enum.
    Fast-fails if an invalid event type is provided rather than guessing via regex.
    """
    if isinstance(event_type, TraceEventType):
        return event_type

    if isinstance(event_type, str):
        try:
            return TraceEventType[event_type.upper()]
        except KeyError:
            pass

    raise ValueError(f"Invalid TraceEventType provided: '{event_type}'")


async def emit_telemetry(
        event: TraceEvent,
        bus: Optional[TelemetryBus] = None,
) -> None:
    """
    Async dispatch of trace events through an injected TelemetryBus interface.

    Args:
        event: The strongly-typed TraceEvent instance.
        bus: The injected TelemetryBus implementation. If None, telemetry emission is skipped.
    """
    if bus is None:
        return

    if not isinstance(bus, TelemetryBus) and not hasattr(bus, "emit"):
        logger.warning(
            f"Invalid telemetry_bus injected: {type(bus).__name__}. "
            "Must implement TelemetryBus Protocol."
        )
        return

    try:
        if hasattr(event, "model_dump"):
            event_dict = event.model_dump(mode="json")
        elif hasattr(event, "dict"):
            event_dict = event.dict()
        else:
            event_dict = dict(event)

        res = bus.emit(event_dict)
        if inspect.isawaitable(res):
            await res
    except Exception as err:
        logger.error(f"TelemetryBus emit call failed: {err}", exc_info=True)