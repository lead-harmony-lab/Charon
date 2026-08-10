"""
charon/agents/__init__.py
System Version: v0.3.3 | File Revision: 1.0.0

Core Agent Framework Package.
Houses base agent classes, execution contracts, and agent lifecycle utilities.
"""

from charon.agents.base import BaseAgent, CapabilityType, SkillContract

__all__ = ["BaseAgent", "CapabilityType", "SkillContract"]