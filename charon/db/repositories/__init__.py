"""
charon/db/repositories/__init__.py

Module: Data Access Layer for system state.
Quarantines all raw SQL and connection logic away from orchestrator, state machine, and skill registries.
"""
from .audit import AuditRepository
from .permission import PermissionRepository
from .prompts import PromptRepository
from .role import RoleRepository
from .agent import AgentRepository
from .gap import SkillGapRepository
from .skill import SkillRepository
from .task import TaskRepository
from .ticker import TickerRepository

__all__ = [
    "AgentRepository",
    "SkillGapRepository",
    "SkillRepository",
    "TaskRepository",
    "TickerRepository",
    "PermissionRepository",
    "AuditRepository",
    "PromptRepository",
]