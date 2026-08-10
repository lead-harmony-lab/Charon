"""
charon/intent/__init__.py
System Version: v0.1.0 | File Revision: 1.3.0

Top-level intent package interface.
Re-exports core agent enums, manifests, routing models, parser engine, and universal payloads.
"""

from charon.intent.base import (
    BaseAgentPayload,
    MemoryCandidate,
    StrictBaseModel,
)
from charon.intent.manifests import (
    AgentManifest,
    get_agent_manifest,
    get_triage_agent_descriptions,
)
from charon.intent.parser import IntentParser
from charon.intent.payloads.dynamic import DynamicActionPayload
from charon.intent.routing import IntentExtraction, RoutingPayload

__all__ = [
    # Base
    "StrictBaseModel",
    "MemoryCandidate",
    "BaseAgentPayload",
    # Manifests
    "AgentManifest",
    "get_agent_manifest",
    "get_triage_agent_descriptions",
    # Engine
    "IntentParser",
    # Routing
    "RoutingPayload",
    "IntentExtraction",
    # Universal Dynamic Payloads
    "DynamicActionPayload",
]