"""
charon/core/dispatcher/__init__.py
System Version: v0.1.0 | Package Revision: 3.2.1

Package entrypoint for specialist agent dispatching.
Exposes the core AgentDispatcher class lazily to prevent circular import loops.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from charon.core.dispatcher.dispatcher import AgentDispatcher

__all__ = ["AgentDispatcher"]


def __getattr__(name: str) -> Any:
    """Lazy-load AgentDispatcher on demand."""
    if name == "AgentDispatcher":
        from charon.core.dispatcher.dispatcher import AgentDispatcher

        return AgentDispatcher
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")