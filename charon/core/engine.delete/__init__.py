"""
charon/core/engine/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: charon.core.engine package.
Exports OrchestrationEngine alongside sub-modules.
"""

from charon.core.orchestration.dag_executor import DAGPlanExecutor
from charon.core.orchestration.engine import OrchestrationEngine
from charon.core.orchestration.self_healing import SelfHealingHandler
from charon.core.orchestration.synthesizer import OutputSynthesizer

__all__ = [
    "OrchestrationEngine",
    "OutputSynthesizer",
    "SelfHealingHandler",
    "DAGPlanExecutor",
]
