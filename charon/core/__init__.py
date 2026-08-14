"""
charon/core/__init__.py
System Version: v0.9.1 | File Revision: 9.1.0

Module: Core orchestration, execution envelopes, and utility primitives.
Refactored for the Active Execution Envelope (Work Contract) paradigm.
"""

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.session import SessionGateway
from charon.core.prompts import (
    CHARON_ROUTING_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)
from charon.core.utils import (
    clean_json_string,
    get_schema_json,
)

__all__ = [
    # Stateful Reflection & Blackboard
    "TaskBlackboard",
    "TaskStatus",
    "EscalationLevel",
    "UnfulfilledRequirement",

    # Session Gateway (Single Entry Point)
    "SessionGateway",

    # Utility Primitives
    "clean_json_string",
    "get_schema_json",
]