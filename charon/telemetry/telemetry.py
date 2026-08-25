"""
charon/telemetry/telemetry.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Telemetry dispatch utilities for strongly-typed event streaming.
Enforces the TelemetryBus Protocol for dependency injection.
"""

import inspect
import logging
from typing import Any, Dict, Optional, Protocol, Union, runtime_checkable

from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus as global_telemetry_bus

logger = logging.getLogger("Charon.Telemetry")


@runtime_checkable
class TelemetryBus(Protocol):
    def emit(self, event: Union[TraceEvent, Dict[str, Any]]) -> Any:
        ...


def resolve_trace_event_type(event_type: Any) -> TraceEventType:
    if isinstance(event_type, TraceEventType):
        return event_type

    if isinstance(event_type, str):
        try:
            return TraceEventType[event_type.upper()]
        except KeyError:
            pass

    raise ValueError(f"Invalid TraceEventType provided: '{event_type}'")


async def emit_telemetry(
    event: Union[TraceEvent, Dict[str, Any]],
    bus: Optional[TelemetryBus] = None,
) -> None:
    """Async dispatch of trace events. Falls back to global singleton if bus is None."""
    target_bus = bus if bus is not None else global_telemetry_bus

    if not hasattr(target_bus, "emit"):
        logger.warning(
            f"Invalid telemetry_bus injected: {type(target_bus).__name__}. "
            "Must implement TelemetryBus Protocol."
        )
        return

    try:
        res = target_bus.emit(event)
        if inspect.isawaitable(res):
            await res
    except Exception as err:
        logger.error(f"TelemetryBus emit call failed: {err}", exc_info=True)