"""
charon/cli/librarian/service.py
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from charon.cli.librarian.db import (
    register_and_bind_skill_db,
    unregister_skill_db,
)

logger = logging.getLogger("charon.cli.librarian.service")


def register_and_bind_skill(
    skill_manifest: Dict[str, Any],
    entry_file_path: Path,
    target_agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    initial_status: str = "ACTIVE",
) -> None:
    """
    Executes V2 skill lifecycle registration in an atomic, scoped transaction.
    Aligns with the Active Execution Envelope (Work Contract) paradigm.
    """
    skill_id = skill_manifest.get("skill_id")
    if not skill_id:
        raise ValueError("Skill manifest must contain a valid 'skill_id'.")

    # Enforce namespace collision guardrails for system skills
    if skill_manifest.get("skill_type") == "system" and not skill_id.startswith("core.system."):
        logger.warning(f"[{skill_id}] System skills should follow the 'core.system.*' naming convention.")

    version = skill_manifest.get("version", "1.0.0")
    category = skill_manifest.get("category", "General")
    global_description = skill_manifest.get("description", "")

    # System requirements remain at the global level
    sys_reqs = json.dumps(skill_manifest.get("system_requirements", []))

    allowed_agents = skill_manifest.get("allowed_agents", ["*"])
    if isinstance(allowed_agents, str):
        allowed_agents = [allowed_agents]

    is_global = 1 if ("*" in allowed_agents or skill_manifest.get("is_global", False)) else 0

    # Extract the V2 actions array
    actions_list = skill_manifest.get("actions", [])
    if not actions_list:
        logger.warning(f"[{skill_id}] No 'actions' array found. The skill will have no executable envelopes.")

    resolved_entry_path = str(entry_file_path.resolve())

    register_and_bind_skill_db(
        skill_id=skill_id,
        actions_list=actions_list,
        version=version,
        category=category,
        global_description=global_description,
        sys_reqs=sys_reqs,
        resolved_entry_path=resolved_entry_path,
        initial_status=initial_status,
        is_global=is_global,
        allowed_agents=allowed_agents,
        target_agent_id=target_agent_id,
        db_path=db_path,
    )

    logger.info(f"[SERVICE] Successfully registered V2 Work Contract '{skill_id}' in state DB.")