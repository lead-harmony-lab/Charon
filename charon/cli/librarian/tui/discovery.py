"""
charon/cli/librarian/tui/discovery.py
System Version: v0.2.0 | File Revision: 3.0.0

Module: Discovery, system dependency validation, and manifest inspection UI orchestrator.
Database operations are fully decoupled and delegated to charon.cli.librarian.db.
"""

import importlib.util
import json
import logging
from pathlib import Path
import shutil
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
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.tui.discovery")

PYPI_TO_MODULE_MAP = {
    "beautifulsoup4": "bs4",
    "paho-mqtt": "paho",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
}


def is_requirement_installed(req: str) -> bool:
    """Checks if a requirement exists as an OS binary on $PATH or an importable Python module."""
    if shutil.which(req):
        return True

    cleaned_req = req.strip().lower()
    module_name = PYPI_TO_MODULE_MAP.get(cleaned_req, cleaned_req)

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def get_active_db_agent_ids() -> Set[str]:
    """Facade for active agent lookup."""
    return get_active_agent_ids()


def _sync_manifest_allowed_agents(skill_id: str, allowed_agents: List[str]) -> None:
    """Locates manifest.json on disk for skill_id and updates its allowed_agents key."""
    roots = [PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR, PKG_STAGED_SKILLS_DIR]
    norm_id = skill_id.lower().replace("sk_", "")

    for root in roots:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                sid = data.get("skill_id", manifest_path.parent.name)
                sid_norm = sid.lower().replace("sk_", "")

                if sid == skill_id or sid_norm == norm_id or manifest_path.parent.name == skill_id:
                    data["allowed_agents"] = allowed_agents
                    with open(manifest_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    logger.debug(f"Updated allowed_agents for '{skill_id}' in {manifest_path}")
                    return
            except Exception as e:
                logger.warning(f"Failed to sync manifest allowed_agents at {manifest_path}: {e}")


def grant_agent_permission(agent_id: str, skill_id: str) -> None:
    """Grants an agent permission for a skill in agent_skill_map and updates manifest.json."""
    success, target_sk_id, authorized_agents = grant_agent_permission_db(agent_id, skill_id)
    if success and target_sk_id:
        _sync_manifest_allowed_agents(target_sk_id, authorized_agents)


def revoke_agent_permission(agent_id: str, skill_id: str) -> None:
    """Revokes an agent's permission for a skill in agent_skill_map and updates manifest.json."""
    success, target_sk_id, remaining_agents = revoke_agent_permission_db(agent_id, skill_id)
    if success and target_sk_id:
        _sync_manifest_allowed_agents(target_sk_id, remaining_agents)


def set_agent_default_skill(agent_id: str, skill_id: str) -> bool:
    """Binds a skill as default_action target for an agent in Schema V3."""
    return set_agent_default_skill_db(agent_id, skill_id)


def discover_skills() -> List[Dict[str, Any]]:
    """Scans search roots and returns enriched skill records validated against DB permissions."""
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
                skill_id = data.get("skill_id", folder_name)
                norm_id = skill_id.lower().replace("sk_", "")
                sk_id = f"sk_{norm_id}"

                sys_reqs = data.get("system_requirements", [])
                missing_reqs = [req for req in sys_reqs if not is_requirement_installed(req)]

                actions = data.get("supported_actions", {})
                action_keys = list(actions.keys()) if isinstance(actions, dict) else [str(a) for a in actions]

                category = data.get("category")
                if not category or category == "General":
                    if any("kicad" in a or "cad" in a for a in action_keys):
                        category = "Hardware & EDA"
                    elif any("pdf" in a or "ocr" in a or "chunk" in a for a in action_keys):
                        category = "Document Processing"
                    elif any("vector" in a or "prune" in a for a in action_keys):
                        category = "Data & Embeddings"
                    else:
                        category = "General / Utility"

                auth_set = (
                    skill_permissions.get(skill_id, set())
                    | skill_permissions.get(norm_id, set())
                    | skill_permissions.get(sk_id, set())
                    | skill_permissions.get(folder_name, set())
                )
                for act in action_keys:
                    auth_set |= skill_permissions.get(act, set())

                authorized_agents = sorted(list(auth_set))

                if "allowed_agents" not in data:
                    data["allowed_agents"] = authorized_agents
                    try:
                        with open(manifest_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                        logger.info(f"Upgraded prototype manifest standard at {manifest_path}")
                    except Exception as e:
                        logger.warning(f"Failed to save upgraded manifest at {manifest_path}: {e}")

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
                    "version": data.get("version", "1.0.0"),
                    "description": data.get("description", "No description provided."),
                    "folder_name": folder_name,
                    "manifest_path": manifest_path,
                    "stage": data.get("stage", stage),
                    "category": category,
                    "allowed_agents": data.get("allowed_agents", []),
                    "authorized_agents": authorized_agents,
                    "default_for_agents": default_for_agents,
                    "system_requirements": sys_reqs,
                    "missing_requirements": missing_reqs,
                    "supported_actions": actions,
                    "health_status": "HEALTHY" if not missing_reqs else "MISSING_PREREQ",
                }
            except Exception as e:
                logger.warning(f"Failed to load or parse skill manifest at {manifest_path}: {e}")
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
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

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

    data["category"] = skill["category"]
    data["version"] = skill.get("version", "1.0.0")
    data["description"] = skill.get("description", "")

    if "allowed_agents" not in data:
        data["allowed_agents"] = skill.get("authorized_agents", [])

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    librarian.reindex_skills()