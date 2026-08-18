"""
charon/agents/__init__.py
System Version: v0.4.0 | File Revision: 2.0.0

Core Agent Framework Package.
Houses base agent classes, execution contracts, and agent lifecycle utilities.
Updated to support the Work Contract (Default Action) execution paradigm.
"""

from charon.agents.base import BaseAgent, CapabilityType, SkillContract
from charon.agents.runtime import RuntimeAgent

__all__ = [
    "BaseAgent",
    "CapabilityType",
    "SkillContract",
    "RuntimeAgent"
]