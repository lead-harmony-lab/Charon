"""
charon/core/prompts.py
System Version: v0.3.0 | File Revision: 3.2.0

Module: Dynamic prompt generation and ACK formatting adhering strictly to the
Janitorial Anchor Directive (Role-based abstraction, DB-driven prompts, and
SkillLibrarian display accessors).
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.core.skills.librarian import SkillLibrarian
from charon.db.repositories.prompts import PromptRepository

logger = logging.getLogger("Charon.Core.Prompts")

# Fallback keys used to load base system prompts
ROUTING_PROMPT_KEY = "system_routing_base"
EXTRACTION_PROMPT_KEY = "system_extraction_base"

# Static fallback templates when DB system prompts are empty or unpopulated
DEFAULT_ROUTING_PROMPT = """You are Charon's Intent Routing System.
Analyze user requests and route them to the appropriate active role based on the registered roster below.

{dynamic_roster}"""

DEFAULT_EXTRACTION_PROMPT = """You are Charon's Action Parameter Extractor.
Extract parameters matching the registered action schema for the target role.

{dynamic_capabilities}"""


def _fetch_db_prompt_template(
    prompt_key: str,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Retrieves a system prompt template strictly via PromptRepository.
    Falls back to static default constants if no custom prompt is defined.
    """
    repo = repo or PromptRepository(db_path)
    role_target = "role_planner" if "routing" in prompt_key else "default_system_generalist"

    template = repo.get_system_prompt_template(role_target)
    if template:
        return template

    # Fall back to hardcoded default constants
    if prompt_key == ROUTING_PROMPT_KEY:
        return DEFAULT_ROUTING_PROMPT
    if prompt_key == EXTRACTION_PROMPT_KEY:
        return DEFAULT_EXTRACTION_PROMPT

    return "{dynamic_content}"


def build_routing_prompt(
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds the routing prompt by populating DB prompt templates
    with available system_roles rather than raw agent_ids.
    """
    repo = repo or PromptRepository(db_path)
    roster_items = repo.get_active_role_roster()

    roster_lines = [
        f"- {item['role_name']}: {item['description']}" for item in roster_items
    ]

    dynamic_roster = "\n".join(roster_lines) if roster_lines else "NO ACTIVE ROLES REGISTERED."

    # Load base prompt template directly from database / fallbacks
    base_template = _fetch_db_prompt_template(ROUTING_PROMPT_KEY, repo=repo, db_path=db_path)

    if "{dynamic_roster}" in base_template:
        return base_template.format(dynamic_roster=dynamic_roster)

    return f"{base_template}\n\nACTIVE ROLES:\n{dynamic_roster}"


def build_extraction_prompt(
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds extraction capabilities mapped across roles and skill registries.
    """
    repo = repo or PromptRepository(db_path)
    capabilities = repo.get_role_capabilities()

    capability_lines = []
    current_role = ""

    for row in capabilities:
        role_name = row["role_name"]
        if role_name != current_role:
            capability_lines.append(f"\nFOR ROLE {role_name.upper()}:")
            current_role = role_name

        action = row["action_name"]
        desc = row["description"]
        params = row["parameters"] or "{}"

        capability_lines.append(
            f'    - {desc} -> Set "action": "{action}", matching schema: {params}'
        )

    dynamic_capabilities = (
        "\n".join(capability_lines) if capability_lines else "NO ACTIVE SKILLS REGISTERED."
    )

    # Load base extraction prompt template directly from database / fallbacks
    base_template = _fetch_db_prompt_template(EXTRACTION_PROMPT_KEY, repo=repo, db_path=db_path)

    if "{dynamic_capabilities}" in base_template:
        return base_template.format(dynamic_capabilities=dynamic_capabilities)

    return f"{base_template}\n\nACTIVE CAPABILITIES:\n{dynamic_capabilities}"


def get_agent_ack(
    agent_id_or_role: str,
    action: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Formats a status acknowledgment using SkillLibrarian presentation accessors
    to resolve human-readable display names instead of leaking raw IDs.
    """
    params = parameters or {}
    target = params.get("target_path") or params.get("query") or params.get("command") or ""

    # Always retrieve presentation label via SkillLibrarian accessor
    display_name = SkillLibrarian.get_display_name_for_role(agent_id_or_role)
    if display_name == agent_id_or_role:
        display_name = SkillLibrarian.get_display_name_for_agent(agent_id_or_role)

    if target:
        clean_target = str(target).replace(os.path.expanduser("~"), "~")
        return f"[{display_name}: Executing {action} on '{clean_target}']"

    repo = repo or PromptRepository(db_path)
    fallback = repo.get_default_action_for_identifier(agent_id_or_role) or "Processing request."

    return f"[{display_name}: {fallback}]"


def __getattr__(name: str) -> Any:
    """
    Backward-compatibility interface resolving dynamic calls via DB getters.
    """
    if name == "CHARON_ROUTING_PROMPT":
        return build_routing_prompt()
    if name == "EXTRACTION_SYSTEM_PROMPT":
        return build_extraction_prompt()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")