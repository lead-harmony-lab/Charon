"""
charon/core/prompts.py
System Version: v0.5.0 | File Revision: 5.0.0

Module: Pure DB-driven prompt generation adhering strictly to the new Work Contract
routing paradigm (dynamic_routing_rules, route_registry, system_roles).
Zero hardcoded string bias. Zero legacy UI string formatters.
Includes lazy synchronization and skill reindexing triggers on unpopulated database
state to prevent import-time routing crashes during daemon boot.
"""

import logging
from pathlib import Path
from typing import Any, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection
from charon.db.repositories.prompts import PromptRepository

logger = logging.getLogger("charon.core.prompts")


class DynamicRoutingError(RuntimeError):
    """Raised when the database contains no active routing rules or system roles."""
    pass


def fetch_dynamic_routing_context(db_path: Union[str, Path] = STATE_DB_PATH) -> str:
    """
    Constructs the routing context strictly from dynamic_routing_rules.
    Focuses on declarative routing to Roles rather than micro-capabilities.
    """
    query = """
        SELECT trigger, agent_id, description 
        FROM dynamic_routing_rules
        ORDER BY trigger ASC;
    """
    try:
        with get_connection(db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query)
            rules = cursor.fetchall()

        if not rules:
            return ""

        rule_lines = [
            f"- IF request matches '{r['trigger']}' -> ROUTE TASK TO ROLE '{r['agent_id']}' ({r['description']})"
            for r in rules
        ]
        return "\n".join(rule_lines)
    except Exception as err:
        logger.error(f"[Prompts] Failed to query dynamic_routing_rules: {err}")
        return ""


def build_routing_prompt(
    target_role_or_agent: Optional[str] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds the routing prompt purely from active system roles and
    dynamic routing rules in SQLite. Fails fast if no DB state is present.
    Executes a lazy database sync if state is initially empty.
    """
    repo = repo or PromptRepository(db_path)

    # 1. Fetch active role roster
    roster_items = repo.get_active_role_roster() if hasattr(repo, "get_active_role_roster") else []

    # 2. Fetch dynamic routing rules
    routing_rules = fetch_dynamic_routing_context(db_path)

    # Lazy synchronization pass if database context is missing
    if not roster_items and not routing_rules:
        try:
            from charon.cli.librarian.db.sync import run_sync
            run_sync()
            roster_items = repo.get_active_role_roster() if hasattr(repo, "get_active_role_roster") else []
            routing_rules = fetch_dynamic_routing_context(db_path)
        except Exception as err:
            logger.warning(f"[Prompts] Lazy database sync attempt failed: {err}")

    if not roster_items and not routing_rules:
        raise DynamicRoutingError(
            "[FATAL] Cannot build routing prompt: No active system_roles or dynamic_routing_rules "
            "found in charon_state.db."
        )

    roster_lines = [
        f"- Role '{item['role_name']}': {item['description']} (Managed by Work Contract)"
        for item in roster_items
        if isinstance(item, dict)
    ]

    prompt_parts = [
        "You are an orchestration engine. Your job is to route declarative tasks to the appropriate specialized Role.",
        "Do NOT attempt to execute micro-skills yourself. Assign high-level objectives to the roles below."
    ]

    # Optional role-specific system prompt override from agent_registry
    if target_role_or_agent and hasattr(repo, "get_system_prompt_template"):
        custom_base = repo.get_system_prompt_template(target_role_or_agent)
        if custom_base:
            prompt_parts.append(custom_base)

    if roster_lines:
        prompt_parts.append("ACTIVE ROLES:\n" + "\n".join(roster_lines))

    if routing_rules:
        prompt_parts.append("DYNAMIC ROUTING RULES:\n" + routing_rules)

    return "\n\n".join(prompt_parts)


def build_extraction_prompt(
    target_role_or_agent: Optional[str] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds task extraction context mapped across active roles.
    Under the new Work Contract paradigm, this no longer exposes strict micro-tool schemas
    to the LLM. Instead, it provides peripheral capabilities purely as context so the LLM
    knows what a role CAN do when formulating the declarative Work Contract payload.
    """
    repo = repo or PromptRepository(db_path)

    capabilities = repo.get_role_capabilities() if hasattr(repo, "get_role_capabilities") else []

    # Lazy synchronization pass & skill reindexing if skill schema state is missing
    if not capabilities:
        try:
            from charon.cli.librarian.db.sync import run_sync
            from charon.core.skills.librarian import SkillLibrarian

            run_sync()
            librarian = SkillLibrarian.get_instance()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            capabilities = repo.get_role_capabilities() if hasattr(repo, "get_role_capabilities") else []
        except Exception as err:
            logger.warning(f"[Prompts] Lazy database sync/reindex attempt failed: {err}")

    if not capabilities:
        raise DynamicRoutingError(
            "[FATAL] Cannot build extraction prompt: No active skill schemas registered in skill_registry."
        )

    capability_lines = []
    current_role = ""

    for row in capabilities:
        if not isinstance(row, dict):
            continue
        role_name = row.get("role_name", "UNKNOWN")
        if role_name != current_role:
            capability_lines.append(f"\nROLE: {role_name.upper()} (Executes via specialized Work Contract)")
            current_role = role_name

        action = row.get("action_name", "")
        desc = row.get("description", "")

        # We expose what the tool does, but hide the exact micro-schema to force declarative payloads
        capability_lines.append(f"    - Peripheral Capability: {action} ({desc})")

    prompt_parts = []

    if target_role_or_agent and hasattr(repo, "get_system_prompt_template"):
        custom_base = repo.get_system_prompt_template(target_role_or_agent)
        if custom_base:
            prompt_parts.append(custom_base)

    prompt_parts.append(
        "ACTIVE ROLES & PERIPHERAL CAPABILITIES:\n"
        "The following outlines the specialized roles and the internal tools they possess.\n"
        "IMPORTANT: When extracting requirements, do NOT target these micro-tools directly. "
        "Formulate a high-level, declarative task payload for the Role. The Role's Work Contract "
        "will securely manage its own tool schemas and execution context.\n"
        + "\n".join(capability_lines)
    )

    return "\n\n".join(prompt_parts)


def __getattr__(name: str) -> Any:
    """Backward-compatibility interface resolving dynamic calls via DB getters."""
    if name == "CHARON_ROUTING_PROMPT":
        return build_routing_prompt()
    if name == "EXTRACTION_SYSTEM_PROMPT":
        return build_extraction_prompt()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")