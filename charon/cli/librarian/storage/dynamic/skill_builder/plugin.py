"""
Plugin entrypoint module for skill_builder.
Provides programmatic skill creation and lifecycle management for agents.
"""

import json
from pathlib import Path
from typing import Any, Dict

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_create
from charon.cli.librarian.lifecycle import run_promote
from charon.cli.librarian.permissions import run_permission_change
from charon.config.paths import PKG_STAGED_SKILLS_DIR


def handle_build_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    description = params.get("description", "Agent-generated skill.")
    category = params.get("category", "General")
    actions = params.get("actions", {})
    plugin_code = params.get("plugin_code")

    if not skill_id or not plugin_code:
        return {"status": "error", "message": "Missing required parameters: 'skill_id' or 'plugin_code'."}

    if not isinstance(actions, dict):
        return {"status": "error", "message": "'actions' must be a dictionary mapping action_name to description string."}

    ret = run_create(skill_id=skill_id, category=category)
    if ret != 0:
        return {"status": "error", "message": f"Failed to scaffold staging directory for '{skill_id}'."}

    staged_dir = PKG_STAGED_SKILLS_DIR / skill_id
    staged_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "skill_id": skill_id,
        "version": params.get("version", "1.0.0"),
        "description": description,
        "category": category,
        "author": params.get("author", "The_Engineer"),
        "stage": "Staged",
        "shelf_tags": params.get("shelf_tags", []),
        "system_requirements": params.get("system_requirements", []),
        "supported_actions": actions,
    }

    manifest_path = staged_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    plugin_path = staged_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(plugin_code)

    run_sync()

    return {
        "status": "success",
        "skill_id": skill_id,
        "message": f"Skill '{skill_id}' successfully constructed and placed in staged quarantine.",
    }


def handle_authorize_agent(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    agent_name = params.get("agent_name")

    if not skill_id or not agent_name:
        return {"status": "error", "message": "Missing required parameters: 'skill_id' or 'agent_name'."}

    res = run_permission_change(skill_id=skill_id, agent_name=agent_name, action="grant")
    if res == 0:
        return {"status": "success", "message": f"Granted agent '{agent_name}' access to skill '{skill_id}'."}
    return {"status": "error", "message": f"Failed to grant permission for '{agent_name}' on '{skill_id}'."}


def handle_promote_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    if not skill_id:
        return {"status": "error", "message": "Missing required parameter 'skill_id'."}

    res = run_promote(skill_id=skill_id)
    if res == 0:
        return {"status": "success", "skill_id": skill_id, "message": f"Skill '{skill_id}' successfully promoted to dynamic production."}
    return {"status": "error", "message": f"Failed to promote staged skill '{skill_id}'."}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "build_skill":
        return handle_build_skill(params)
    elif action_name == "authorize_agent":
        return handle_authorize_agent(params)
    elif action_name == "promote_skill":
        return handle_promote_skill(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'skill_builder'.")
