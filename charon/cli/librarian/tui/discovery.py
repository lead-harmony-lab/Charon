"""
charon/cli/librarian/tui/discovery.py
System Version: v0.1.0 | File Revision: 2.5.0

Module: V3-aligned skill discovery, manifest parsing, database permission queries,
agent default skill bindings, and decoupled dual-pathway integrity auditing.
"""

import importlib.util
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

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
    """Queries active agent_ids from agent_registry in charon_state.db."""
    if not STATE_DB_PATH.exists():
        return set()
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT agent_id FROM agent_registry WHERE is_active = 1")
            return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.debug(f"Failed to query active agents from state DB: {e}")
        return set()


def resolve_skill_contract(
    cursor: sqlite3.Cursor, identifier: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves any identifier (folder name, manifest ID, DB skill_id, or action_name)
    against skill_registry. Returns (action_name, skill_id).
    """
    if not identifier:
        return (None, None)

    norm_id = identifier.replace("sk_", "").strip()

    # 1. Exact match against action_name or skill_id variants
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE action_name = ? OR skill_id = ? OR skill_id = ? OR action_name = ?
        """,
        (identifier, identifier, f"sk_{norm_id}", norm_id),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    # 2. Path-based resolution (handles Unix '/' and Windows '\' path separators)
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE entry_file_path LIKE ? OR entry_file_path LIKE ?
           OR entry_file_path LIKE ? OR entry_file_path LIKE ?
        """,
        (f"%/{identifier}/%", f"%/{norm_id}/%", f"%\\{identifier}\\%", f"%\\{norm_id}\\%"),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    return (None, None)


def get_skill_permissions() -> Dict[str, Set[str]]:
    """Queries DB agent_skill_map to map authorized agent_ids to skill_ids and action_names."""
    skill_map: Dict[str, Set[str]] = {}

    if not STATE_DB_PATH.exists():
        return skill_map

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT asm.skill_id, asm.agent_id, sr.action_name
                FROM agent_skill_map asm
                LEFT JOIN skill_registry sr ON (asm.skill_id = sr.skill_id OR asm.skill_id = sr.action_name)
                """
            )
            for db_skill_id, agent_id, action_name in cursor.fetchall():
                if db_skill_id:
                    skill_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    skill_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    skill_map.setdefault(action_name, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query permissions from agent_skill_map: {e}")

    return skill_map


def get_skill_defaults() -> Dict[str, Set[str]]:
    """Queries state DB to map skill_ids and action_names to agent_ids using them as default actions."""
    default_map: Dict[str, Set[str]] = {}

    if not STATE_DB_PATH.exists():
        return default_map

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.skill_id, s.action_name, a.agent_id, a.default_action
                FROM agent_registry a
                LEFT JOIN skill_registry s ON (a.default_action = s.action_name OR a.default_action = s.skill_id)
                WHERE a.is_active = 1 AND a.default_action IS NOT NULL
                """
            )
            for db_skill_id, action_name, agent_id, default_action in cursor.fetchall():
                if db_skill_id:
                    default_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    default_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    default_map.setdefault(action_name, set()).add(agent_id)
                if default_action:
                    default_map.setdefault(default_action, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query default action mappings: {e}")

    return default_map


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
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            _, target_sk_id = resolve_skill_contract(cursor, skill_id)
            if not target_sk_id:
                target_sk_id = skill_id

            # Validate skill existence in skill_registry to prevent foreign key violations
            cursor.execute("SELECT 1 FROM skill_registry WHERE skill_id = ?", (target_sk_id,))
            if not cursor.fetchone():
                logger.warning(
                    f"Cannot grant permission: skill '{target_sk_id}' is not yet indexed in skill_registry."
                )
                return

            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id) 
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, target_sk_id),
            )
            conn.commit()

            # Sync updated permissions to disk manifest
            cursor.execute(
                "SELECT DISTINCT agent_id FROM agent_skill_map WHERE skill_id = ?",
                (target_sk_id,),
            )
            authorized_agents = sorted([row[0] for row in cursor.fetchall()])
            _sync_manifest_allowed_agents(target_sk_id, authorized_agents)
    except Exception as e:
        logger.error(f"Failed to grant agent permission: {e}")


def revoke_agent_permission(agent_id: str, skill_id: str) -> None:
    """Revokes an agent's permission for a skill in agent_skill_map and updates manifest.json."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            _, matched_skill_id = resolve_skill_contract(cursor, skill_id)
            target_sk_id = matched_skill_id or skill_id
            norm_id = skill_id.replace("sk_", "")

            cursor.execute(
                """
                DELETE FROM agent_skill_map 
                WHERE agent_id = ? AND (skill_id = ? OR skill_id = ? OR skill_id = ?)
                """,
                (agent_id, skill_id, matched_skill_id or "", f"sk_{norm_id}"),
            )
            conn.commit()

            # Sync remaining permissions to disk manifest
            cursor.execute(
                "SELECT DISTINCT agent_id FROM agent_skill_map WHERE skill_id = ?",
                (target_sk_id,),
            )
            remaining_agents = sorted([row[0] for row in cursor.fetchall()])
            _sync_manifest_allowed_agents(target_sk_id, remaining_agents)
    except Exception as e:
        logger.error(f"Failed to revoke agent permission: {e}")


def set_agent_default_skill(agent_id: str, skill_id: str) -> bool:
    """
    Binds a skill as default_action target for an agent in Schema V3.
    Resolves through skill_registry first. Fails if unresolvable.
    """
    if not STATE_DB_PATH.exists() or not agent_id or not skill_id:
        return False
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()

            action_name, matched_skill_id = resolve_skill_contract(cursor, skill_id)

            if not action_name or not matched_skill_id:
                logger.error(
                    f"Refusing default assignment: '{skill_id}' cannot be resolved in skill_registry."
                )
                return False

            # 1. Update agent_registry default_action contract
            cursor.execute(
                """
                UPDATE agent_registry
                SET default_action = ?, updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ?
                """,
                (action_name, agent_id),
            )

            # 2. Ensure agent_skill_map link exists
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, matched_skill_id),
            )

            # 3. Update is_default state in agent_skill_map if column exists
            try:
                cursor.execute(
                    "UPDATE agent_skill_map SET is_default = 0 WHERE agent_id = ?",
                    (agent_id,),
                )
                cursor.execute(
                    """
                    UPDATE agent_skill_map SET is_default = 1 
                    WHERE agent_id = ? AND (skill_id = ? OR skill_id = ?)
                    """,
                    (agent_id, skill_id, matched_skill_id),
                )
            except sqlite3.OperationalError:
                pass

            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to set default skill for agent '{agent_id}': {e}")
        return False


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

                # Auto-upgrade prototype manifests missing the standard 'allowed_agents' field
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


# ============================================================================
# DECOUPLED DUAL-PATHWAY AUDITING
# ============================================================================

def audit_agent_skill_integrity() -> Dict[str, Any]:
    """
    PATHWAY 1: Database Integrity Audit.
    Validates that active agents have valid default_action targets in skill_registry
    and corresponding authorization entries in agent_skill_map.
    """
    audit_report: Dict[str, Any] = {
        "is_clean": True,
        "orphan_default_actions": [],
        "missing_permission_links": [],
        "active_agents_checked": 0,
    }

    if not STATE_DB_PATH.exists():
        return audit_report

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT 
                    a.agent_id,
                    a.default_action,
                    s.skill_id AS skill_in_registry,
                    asm.skill_id AS linked_in_map
                FROM agent_registry a
                LEFT JOIN skill_registry s ON (a.default_action = s.action_name OR a.default_action = s.skill_id)
                LEFT JOIN agent_skill_map asm ON a.agent_id = asm.agent_id AND s.skill_id = asm.skill_id
                WHERE a.is_active = 1
                """
            )
            rows = cursor.fetchall()
            audit_report["active_agents_checked"] = len(rows)

            for agent_id, default_action, skill_in_registry, linked_in_map in rows:
                if default_action and not skill_in_registry:
                    audit_report["is_clean"] = False
                    audit_report["orphan_default_actions"].append(
                        {"agent_id": agent_id, "default_action": default_action}
                    )
                elif skill_in_registry and not linked_in_map:
                    audit_report["is_clean"] = False
                    audit_report["missing_permission_links"].append(
                        {"agent_id": agent_id, "skill_id": skill_in_registry, "default_action": default_action}
                    )

    except Exception as e:
        logger.error(f"Failed to execute database agent-skill integrity audit: {e}")

    return audit_report


def audit_filesystem_manifest_health() -> Dict[str, Any]:
    """
    PATHWAY 2: Filesystem Health Audit.
    Scans physical disk roots, verifying manifest validation, plugin entrypoints,
    and matching entries in skill_registry.
    """
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


# ============================================================================
# METRICS & STATE DB QUERIES
# ============================================================================

def get_quarantined_orphans_count() -> int:
    """Queries count of quarantined/orphaned skills in charon_state.db."""
    if not STATE_DB_PATH.exists():
        return 0
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_registry WHERE status = 'QUARANTINED'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query quarantined orphans count: {e}")
        return 0


def get_open_gaps_count() -> int:
    """Queries count of open skill gaps in charon_state.db."""
    if not STATE_DB_PATH.exists():
        return 0
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'open'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query open gaps count: {e}")
        return 0


def get_resolved_gaps_count() -> int:
    """Queries count of resolved skill gaps pending database purge."""
    if not STATE_DB_PATH.exists():
        return 0
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'resolved'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query resolved gaps count: {e}")
        return 0


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