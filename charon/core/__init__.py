"""
charon/core/__init__.py
System Version: v0.9.1 | File Revision: 9.1.0

Module: Core orchestration, execution envelopes, and utility primitives.
Refactored for the Active Execution Envelope (Work Contract) paradigm.
"""

from charon.core.coordinator.blackboard import (
    TaskBlackboard,
    TaskStatus,
)
from charon.core.utils import (
    clean_json_string,
    get_schema_json,
)

__all__ = [
    # Stateful Reflection & Blackboard
    "TaskBlackboard",
    "TaskStatus",

    # Utility Primitives
    "clean_json_string",
    "get_schema_json",
]