"""
charon/intent/payloads/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Intent payload schemas package initializer.
Exports universal dynamic payload schema for skill execution.
"""

from charon.intent.payloads.dynamic import DynamicActionPayload

__all__ = [
    "DynamicActionPayload",
]