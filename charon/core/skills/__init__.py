"""
charon/core/skills/__init__.py

Module: Core Skills Package.
Re-exports the dynamic skills API to maintain backward compatibility.
"""

from charon.core.skills.base import BaseSkill
from charon.core.skills.executor import SkillExecutorMixin
from charon.core.skills.indexer import SkillIndexerMixin
from charon.core.skills.librarian import SkillLibrarian
from charon.core.skills.models import ActionMetadata, SkillManifest
from charon.core.skills.query import SkillQueryMixin
from charon.core.skills.roles import RoleResolverMixin
from charon.core.skills.routes import RouteManagerMixin

__all__ = [
    "BaseSkill",
    "ActionMetadata",
    "SkillManifest",
    "SkillLibrarian",
    "RoleResolverMixin",
    "RouteManagerMixin",
    "SkillIndexerMixin",
    "SkillQueryMixin",
    "SkillExecutorMixin",
]