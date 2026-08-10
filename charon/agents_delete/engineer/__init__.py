"""
charon/agents/engineer/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: TheEngineer Agent Package.

Manages self-healing Python script generation, iterative bug resolution,
AST disk artifact auditing, and guarded subshell sandbox execution.
"""

from charon.agents.engineer.agent import (
    TheEngineer,
    VALID_ENGINEER_ACTIONS,
    ACTION_MAP,
)
from charon.agents.engineer.solver import handle_solve_edge_case
from charon.agents.engineer.generator import handle_generate_script_only
from charon.agents.engineer.runner import (
    handle_execute_sandbox_code,
    handle_run_existing_script,
)



__all__ = [
    "TheEngineer",
    "VALID_ENGINEER_ACTIONS",
    "ACTION_MAP",
    "handle_solve_edge_case",
    "handle_generate_script_only",
    "handle_execute_sandbox_code",
    "handle_run_existing_script",
]