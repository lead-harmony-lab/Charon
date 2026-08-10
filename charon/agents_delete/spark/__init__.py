"""
charon/agents/spark/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: The Spark agent package — Electrical & Firmware Domain.
"""

from charon.agents.spark.agent import ACTION_MAP, VALID_SPARK_ACTIONS, TheSpark

__all__ = ["TheSpark", "VALID_SPARK_ACTIONS", "ACTION_MAP"]