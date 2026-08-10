"""
charon/core/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Core orchestration, parsing, dispatching, and utility primitives.
"""

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.dispatcher import AgentDispatcher
from charon.core.session import SessionGateway
from charon.core.parser import IntentParser
from charon.core.prompts import (
    CHARON_ROUTING_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)
from charon.core.utils import (
    clean_json_string,
    get_schema_json,
    normalize_agent,
)

__all__ = [
    # Stateful Reflection & Blackboard
    "TaskBlackboard",
    "TaskStatus",
    "EscalationLevel",
    # Main Orchestration Engine & Dispatcher
    "SessionGateway",
    "AgentDispatcher",
    "IntentParser",
    # Parsing & Schema Utilities
    "clean_json_string",
    "normalize_agent",
    "get_schema_json",
]