"""
System Version: v2.0.0 | File Revision: 3.5.0

Module: Discovery, system dependency validation, and manifest inspection UI orchestrator.
Database operations are fully decoupled and delegated to charon.cli.librarian.db.
Target Standard: Manifest Schema V2 Only.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

from charon.cli.librarian.db import (
    get_active_agent_ids,
    get_open_gaps_count,
    get_quarantined_orphans_count,
    get_resolved_gaps_count,
    get_skill_defaults,
    get_skill_permissions,
    grant_agent_permission_db,
    revoke_agent_permission_db,
    set_agent_default_skill_db,
)
from charon.cli.librarian.validators import verify_system_dependencies
from charon.config.paths import (
    AGENT_REGISTRY_JSON,
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian

logger = logging.getLogger("charon.cli.librarian.tui.discovery")


def get_active_db_agent_ids() -> Set[str]:
    """Facade for active agent lookup."""
    return get_active_agent_ids()


def grant_agent_permission(agent_id: str, skill_id: str) -> None:
    """Grants an agent permission for a skill in agent_skill_map (Database is ground truth)."""
    grant_agent_permission_db(agent_id, skill_id)


def revoke_agent_permission(agent_id: str, skill_id: str) -> None:
    """Revokes an agent's permission for a skill in agent_skill_map (Database is ground truth)."""
    revoke_agent_permission_db(agent_id, skill_id)


def _update_agent_registry_json(agent_id: str, action_name: str) -> bool:
    """Persists default_action change to agent_registry.json on disk."""
    if not AGENT_REGISTRY_JSON.exists():
        logger.error(f"Agent registry JSON file not found at {AGENT_REGISTRY_JSON}")
        return False

    try:
        with open(AGENT_REGISTRY_JSON, "r", encoding="utf-8") as f:
            agents = json.load(f)

        updated = False
        for agent in agents:
            if agent.get("agent_id") == agent_id:
                agent["default_action"] = action_name
                updated = True
                break

        if not updated:
            logger.warning(f"Agent '{agent_id}' not found in {AGENT_REGISTRY_JSON}")
            return False

        with open(AGENT_REGISTRY_JSON, "w", encoding="utf-8") as f:
            json.dump(agents, f, indent=2)

        return True
    except Exception as e:
        logger.error(f"Failed to update agent_registry.json for agent '{agent_id}': {e}")
        return False


def set_agent_default_skill(agent_id: str, action_name: str) -> bool:
    """Binds a skill as default_action target for an agent in Schema V3 across disk and DB."""
    json_updated = _update_agent_registry_json(agent_id, action_name)
    if not json_updated:
        logger.warning(
            f"Could not persist default action '{action_name}' to agent_registry.json for '{agent_id}'."
        )

    success, msg, warn = set_agent_default_skill_db(agent_id, action_name)
    if warn:
        logger.warning(warn)
    if not success:
        logger.error(msg)
    return success and json_updated


def discover_skills() -> List[Dict[str, Any]]:
    """Scans search roots and returns enriched skill records derived from V2 manifests validated against DB permissions."""
    skill_permissions = get_skill_permissions()
    skill_defaults = get_skill_defaults()
    skills_by_id: Dict[str, Dict[str, Any]] = {}

    roots = [
        ("Staged", PKG_STAGED_SKILLS_DIR),
        ("Dynamic", PKG_DYNAMIC_SKILLS_DIR),
        ("Dynamic", DYNAMIC_SKILLS_DIR),
    ]

    for stage, root in roots:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                folder_name = manifest_path.parent.name
                raw_actions = data.get("actions", [])

                # Package identity fallback sequence: package > actions[0].skill_id > folder_name
                package_name = data.get("package")
                if not package_name and raw_actions and isinstance(raw_actions[0], dict):
                    package_name = raw_actions[0].get("skill_id")

                skill_id = package_name or folder_name
                norm_id = skill_id.lower().replace("sk_", "")
                sk_id = f"sk_{norm_id}"

                # Decoupled system requirements verification
                sys_reqs = data.get("system_requirements", [])
                _, missing_reqs = verify_system_dependencies(sys_reqs)

                supported_actions: Dict[str, str] = {}
                primary_action = raw_actions[0] if raw_actions and isinstance(raw_actions[0], dict) else {}
                primary_action_name = primary_action.get("action_name", skill_id)
                primary_handler_name = primary_action.get("handler_name", "N/A")
                primary_description = data.get("description") or primary_action.get("description", "No description provided.")

                for act in raw_actions:
                    if isinstance(act, dict):
                        act_name = act.get("action_name")
                        if act_name:
                            supported_actions[act_name] = act.get("handler_name", "")

                action_keys = list(supported_actions.keys())

                # Manifest Schema V2: skill_type and domain resolution
                skill_type = data.get("skill_type", "tool")
                domain = data.get("domain", "General")
                formatted_type = skill_type.replace("_", " ").title()
                category = f"{domain} / {formatted_type}"

                # Resolve DB-backed authorized agents
                auth_set = (
                    skill_permissions.get(skill_id, set())
                    | skill_permissions.get(norm_id, set())
                    | skill_permissions.get(sk_id, set())
                    | skill_permissions.get(folder_name, set())
                )
                for act in action_keys:
                    auth_set |= skill_permissions.get(act, set())

                authorized_agents = sorted(list(auth_set))

                # Resolve DB-backed defaults
                def_set = (
                    skill_defaults.get(skill_id, set())
                    | skill_defaults.get(norm_id, set())
                    | skill_defaults.get(sk_id, set())
                    | skill_defaults.get(folder_name, set())
                )
                for act in action_keys:
                    def_set |= skill_defaults.get(act, set())

                default_for_agents = sorted(list(def_set))

                skills_by_id[skill_id] = {
                    "skill_id": skill_id,
                    "package": data.get("package", skill_id),
                    "action_name": primary_action_name,
                    "handler_name": primary_handler_name,
                    "version": data.get("version", "2.0.0"),
                    "description": primary_description,
                    "folder_name": folder_name,
                    "manifest_path": manifest_path,
                    "stage": data.get("status", stage),
                    "skill_type": skill_type,
                    "domain": domain,
                    "category": category,
                    "is_global": data.get("is_global", False),
                    "authorized_agents": authorized_agents,
                    "default_for_agents": default_for_agents,
                    "system_requirements": sys_reqs,
                    "missing_requirements": missing_reqs,
                    "supported_actions": supported_actions,
                    "health_status": "HEALTHY" if not missing_reqs else "MISSING_PREREQ",
                }
            except Exception as e:
                logger.warning(f"Failed to load or parse V2 skill manifest at {manifest_path}: {e}")
                continue

    return list(skills_by_id.values())


def audit_agent_skill_integrity() -> Dict[str, Any]:
    """PATHWAY 1: Database Integrity Audit. Delegates query to pure database audit module."""
    from charon.cli.librarian.db import perform_state_audit
    audit_data = perform_state_audit()
    return {
        "is_clean": audit_data.get("drift_count", 0) == 0,
        "orphan_default_actions": audit_data.get("orphaned_mappings", []),
        "missing_permission_links": [],
        "active_agents_checked": len(audit_data.get("skills", [])),
    }


def audit_filesystem_manifest_health() -> Dict[str, Any]:
    """PATHWAY 2: Filesystem Health Audit. Verifies physical disk roots against DB state."""
    audit_report: Dict[str, Any] = {
        "is_healthy": True,
        "unregistered_disk_skills": [],
        "missing_plugin_files": [],
        "corrupt_manifests": [],
    }

    if not STATE_DB_PATH.exists():
        return audit_report

    registered_paths: Set[str] = set()
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entry_file_path FROM skill_registry")
            registered_paths = {
                str(Path(row[0]).resolve()) for row in cursor.fetchall() if row[0]
            }
    except Exception as e:
        logger.error(f"Failed to query skill_registry paths: {e}")

    roots = [PKG_STAGED_SKILLS_DIR, PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR]

    for root in roots:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                plugin_path = manifest_path.parent / "plugin.py"
                if not plugin_path.exists():
                    audit_report["is_healthy"] = False
                    audit_report["missing_plugin_files"].append(str(manifest_path.parent))

                str_plugin_path = str(plugin_path.resolve())
                if registered_paths and str_plugin_path not in registered_paths:
                    audit_report["is_healthy"] = False
                    audit_report["unregistered_disk_skills"].append(
                        {"folder": manifest_path.parent.name, "path": str(manifest_path)}
                    )

            except Exception as e:
                audit_report["is_healthy"] = False
                audit_report["corrupt_manifests"].append({"path": str(manifest_path), "error": str(e)})

    return audit_report


def save_manifest(skill: Dict[str, Any], librarian: SkillLibrarian) -> None:
    """Saves non-permission manifest changes to disk and triggers librarian re-indexing."""
    manifest_path = skill["manifest_path"]
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Purge deprecated V1 key and persist V2 schema keys
    data.pop("category", None)
    data["skill_type"] = skill.get("skill_type", data.get("skill_type", "tool"))
    data["domain"] = skill.get("domain", data.get("domain", "General"))
    data["version"] = skill.get("version", "2.0.0")
    if "is_global" in skill:
        data["is_global"] = skill["is_global"]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    librarian.reindex_skills()