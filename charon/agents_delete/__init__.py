"""
charon/agents/__init__.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Central Agent Package Gateway with Lazy Loading. Uses PEP 562 dynamic attribute resolution (__getattr__) to import agent modules
on-demand. This reduces startup latency and memory overhead by deferring heavy
imports (e.g., ChromaDB, PyPDF, embedding models, CAD tools) until an agent is accessed.
"""

import importlib
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Type

# Static analyzer imports for IDE autocompletion / inspection without runtime performance penalty
if TYPE_CHECKING:
    from charon.agents.archivist import TheArchivist
    from charon.agents.cleaner import TheCleaner
    from charon.agents.engineer import TheEngineer
    from charon.agents.generalist import TheGeneralist
    from charon.agents.machinist import TheMachinist
    from charon.agents.overseer import TheOverseer
    from charon.agents.planner import ThePlanner
    from charon.agents.quartermaster import TheQuartermaster
    from charon.agents.scout import TheScout
    from charon.agents.spark import TheSpark
    from charon.agents.steward import TheSteward

# Registry mapping: (module_path, target_class_name)
_LAZY_AGENT_REGISTRY: Dict[str, Tuple[str, str]] = {
    # Class exports
    "TheArchivist": ("charon.agents.archivist", "TheArchivist"),
    "TheCleaner": ("charon.agents.cleaner", "TheCleaner"),
    "TheEngineer": ("charon.agents.engineer", "TheEngineer"),
    "TheGeneralist": ("charon.agents.generalist", "TheGeneralist"),
    "TheMachinist": ("charon.agents.machinist", "TheMachinist"),
    "TheOverseer": ("charon.agents.overseer", "TheOverseer"),
    "ThePlanner": ("charon.agents.planner", "ThePlanner"),
    "TheQuartermaster": ("charon.agents.quartermaster", "TheQuartermaster"),
    "TheScout": ("charon.agents.scout", "TheScout"),
    "TheSpark": ("charon.agents.spark", "TheSpark"),
    "TheSteward": ("charon.agents.steward", "TheSteward"),
    # Normalized lookup aliases
    "archivist": ("charon.agents.archivist", "TheArchivist"),
    "the_archivist": ("charon.agents.archivist", "TheArchivist"),
    "cleaner": ("charon.agents.cleaner", "TheCleaner"),
    "the_cleaner": ("charon.agents.cleaner", "TheCleaner"),
    "engineer": ("charon.agents.engineer", "TheEngineer"),
    "the_engineer": ("charon.agents.engineer", "TheEngineer"),
    "generalist": ("charon.agents.generalist", "TheGeneralist"),
    "the_generalist": ("charon.agents.generalist", "TheGeneralist"),
    "machinist": ("charon.agents.machinist", "TheMachinist"),
    "the_machinist": ("charon.agents.machinist", "TheMachinist"),
    "overseer": ("charon.agents.overseer", "TheOverseer"),
    "the_overseer": ("charon.agents.overseer", "TheOverseer"),
    "planner": ("charon.agents.planner", "ThePlanner"),
    "the_planner": ("charon.agents.planner", "ThePlanner"),
    "quartermaster": ("charon.agents.quartermaster", "TheQuartermaster"),
    "the_quartermaster": ("charon.agents.quartermaster", "TheQuartermaster"),
    "scout": ("charon.agents.scout", "TheScout"),
    "the_scout": ("charon.agents.scout", "TheScout"),
    "spark": ("charon.agents.spark", "TheSpark"),
    "the_spark": ("charon.agents.spark", "TheSpark"),
    "steward": ("charon.agents.steward", "TheSteward"),
    "the_steward": ("charon.agents.steward", "TheSteward"),
}

# Symbols exposed for wildcard imports (`from charon.agents import *`)
__all__ = [
    "TheArchivist",
    "TheCleaner",
    "TheEngineer",
    "TheGeneralist",
    "TheMachinist",
    "TheOverseer",
    "ThePlanner",
    "TheQuartermaster",
    "TheScout",
    "TheSpark",
    "TheSteward",
    "get_agent_class",
    "list_agents",
]


def __getattr__(name: str) -> Any:
    """Lazy-loads agent classes when accessed directly as module attributes.

    Example:
        from charon.agents import TheSpark  # Module imported only here
    """
    if name in _LAZY_AGENT_REGISTRY:
        module_path, class_name = _LAZY_AGENT_REGISTRY[name]
        module = importlib.import_module(module_path)
        agent_cls = getattr(module, class_name)

        # Cache on module level so subsequent accesses bypass __getattr__
        globals()[name] = agent_cls
        return agent_cls

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> List[str]:
    """Ensures IDE autocompletion and REPL tab-completion work seamlessly."""
    return sorted(list(set(list(__all__) + list(_LAZY_AGENT_REGISTRY.keys()))))


def get_agent_class(agent_name: str) -> Type[Any]:
    """Dynamically loads and returns an agent class by identifier, class name, or alias.

    Args:
        agent_name: Registered alias or class name (e.g., 'spark', 'the-spark', 'TheSpark').

    Returns:
        The target Agent class type.

    Raises:
        ValueError: If the agent identifier cannot be resolved to a registered agent.
    """
    raw_key = str(agent_name).strip()

    # Try exact lookup first
    if raw_key in _LAZY_AGENT_REGISTRY:
        module_path, class_name = _LAZY_AGENT_REGISTRY[raw_key]
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    # Normalize lookup key (lowercase, replace spaces and hyphens with underscores)
    normalized = raw_key.lower().replace(" ", "_").replace("-", "_")

    lookup_candidates = [
        normalized,
        f"the_{normalized}" if not normalized.startswith("the_") else normalized,
        normalized.removeprefix("the_"),
    ]

    for candidate in lookup_candidates:
        if candidate in _LAZY_AGENT_REGISTRY:
            module_path, class_name = _LAZY_AGENT_REGISTRY[candidate]
            module = importlib.import_module(module_path)
            return getattr(module, class_name)

    available = ", ".join(list_agents(canonical_only=True))
    raise ValueError(
        f"Unknown agent '{agent_name}'. Available registered agents: [{available}]"
    )


def list_agents(canonical_only: bool = True) -> List[str]:
    """Returns a sorted list of unique registered agent identifiers without importing modules.

    Args:
        canonical_only: If True, returns only primary class names (e.g., 'TheSpark').
                        If False, returns all registered aliases and lookup keys.
    """
    if canonical_only:
        return sorted(list(set(class_name for _, class_name in _LAZY_AGENT_REGISTRY.values())))
    return sorted(list(set(_LAZY_AGENT_REGISTRY.keys())))