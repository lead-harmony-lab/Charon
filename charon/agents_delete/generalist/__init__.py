"""
charon/agents/generalist/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Generalist Agent Package Exporter.
"""

from charon.agents.generalist.agent import TheGeneralist

# Alias to satisfy the dynamic router's lowercase triage mapping
generalist = TheGeneralist

__all__ = ["TheGeneralist", "generalist"]