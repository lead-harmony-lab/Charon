"""
charon/core/prompts.py
System Version: v0.4.0 | File Revision: 4.0.0

Module: Pure DB-driven prompt generation and ACK formatting adhering strictly to
dynamic routing tables (dynamic_routing_rules, route_registry, system_roles).
Zero hardcoded string bias. Zero static fallbacks.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.core.skills.librarian import SkillLibrarian
from charon.db.connection import get_connection
from charon.db.repositories.prompts import PromptRepository

logger = logging.getLogger("Charon.Core.Prompts")


class DynamicRoutingError(RuntimeError):
    """Raised when the database contains no active routing rules or system roles."""
    pass


def fetch_dynamic_routing_context(db_path: Union[str, Path] = STATE_DB_PATH) -> str:
    """
    Constructs the routing context strictly from dynamic_routing_rules.
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
            f"- IF request matches '{r['trigger']}' -> ROUTE TO '{r['agent_id']}' ({r['description']})"
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
    """
    repo = repo or PromptRepository(db_path)

    # 1. Fetch active role roster
    roster_items = repo.get_active_role_roster() if hasattr(repo, "get_active_role_roster") else []

    # 2. Fetch dynamic routing rules
    routing_rules = fetch_dynamic_routing_context(db_path)

    if not roster_items and not routing_rules:
        raise DynamicRoutingError(
            "[FATAL] Cannot build routing prompt: No active system_roles or dynamic_routing_rules "
            "found in charon_state.db."
        )

    roster_lines = [
        f"- Role '{item['role_name']}': {item['description']}"
        for item in roster_items
        if isinstance(item, dict)
    ]

    prompt_parts = []

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
    Dynamically builds capability extraction schemas mapped across active roles
    and skill registries directly from SQLite.
    """
    repo = repo or PromptRepository(db_path)

    capabilities = repo.get_role_capabilities() if hasattr(repo, "get_role_capabilities") else []
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
            capability_lines.append(f"\nFOR ROLE {role_name.upper()}:")
            current_role = role_name

        action = row.get("action_name", "")
        desc = row.get("description", "")
        params = row.get("parameters") or "{}"

        capability_lines.append(
            f'    - {desc} -> Action: "{action}", Schema: {params}'
        )

    prompt_parts = []

    if target_role_or_agent and hasattr(repo, "get_system_prompt_template"):
        custom_base = repo.get_system_prompt_template(target_role_or_agent)
        if custom_base:
            prompt_parts.append(custom_base)

    prompt_parts.append("ACTIVE CAPABILITIES:\n" + "\n".join(capability_lines))

    return "\n\n".join(prompt_parts)


def get_agent_ack(
    agent_id_or_role: str,
    action: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Formats a status acknowledgment using SkillLibrarian presentation accessors
    to resolve human-readable display names dynamically from DB state.
    """
    params = parameters or {}
    target = params.get("target_path") or params.get("query") or params.get("command") or ""

    display_name = SkillLibrarian.get_display_name_for_role(agent_id_or_role)
    if display_name == agent_id_or_role:
        display_name = SkillLibrarian.get_display_name_for_agent(agent_id_or_role)

    if target:
        clean_target = str(target).replace(os.path.expanduser("~"), "~")
        return f"[{display_name}: Executing {action} on '{clean_target}']"

    repo = repo or PromptRepository(db_path)
    fallback = "Processing request."
    try:
        if hasattr(repo, "get_default_action_for_identifier") and callable(repo.get_default_action_for_identifier):
            fallback = repo.get_default_action_for_identifier(agent_id_or_role) or fallback
    except Exception as err:
        logger.debug(f"[Prompts] Failed to query default action for identifier '{agent_id_or_role}': {err}")

    return f"[{display_name}: {fallback}]"


def __getattr__(name: str) -> Any:
    """Backward-compatibility interface resolving dynamic calls via DB getters."""
    if name == "CHARON_ROUTING_PROMPT":
        return build_routing_prompt()
    if name == "EXTRACTION_SYSTEM_PROMPT":
        return build_extraction_prompt()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")