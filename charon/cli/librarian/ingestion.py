"""
charon/cli/librarian/ingestion.py
System Version: v0.4.0 | File Revision: 4.0.1

Module: Core headless engine for dynamic skill creation, quarantine sanitization,
and defensive zero-trust file ingestion. Completely decoupled from agent binding
and rich console layers. Enforces canonical naming and database schema constraints.
"""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from charon.cli.librarian.db import flag_quarantined_orphans, register_skill_in_db
from charon.cli.librarian.utils import (
    SKILLS_TEMPLATES_DIR,
    derive_action_name,
    get_template_content,
    slugify,
)
from charon.cli.librarian.validators import verify_plugin_entrypoint
from charon.config.paths import (
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_QUARANTINE_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)

# -----------------------------------------------------------------------------
# Module Exports / Path Aliases
# -----------------------------------------------------------------------------
SKILLS_QUARANTINE_DIR = PKG_QUARANTINE_SKILLS_DIR
SKILLS_STAGED_DIR = PKG_STAGED_SKILLS_DIR
SKILLS_DYNAMIC_DIR = PKG_DYNAMIC_SKILLS_DIR


def get_quarantine_skills_summary() -> List[Dict[str, str]]:
    """Data Provider: Inspects the quarantine buffer for TUI renderers."""
    if not PKG_QUARANTINE_SKILLS_DIR.exists():
        return []

    quarantine_items = sorted(
        [p for p in PKG_QUARANTINE_SKILLS_DIR.iterdir() if p.name != ".gitkeep"],
        key=lambda x: (not x.is_dir(), x.name),
    )

    summary = []
    for item in quarantine_items:
        if item.is_dir():
            report_file = item / ".validation_report.json"
            status = "Rejected (Check Report)" if report_file.exists() else "Pending Sanitization"
            summary.append({
                "name": item.name,
                "type": "Directory Package",
                "status": status,
                "path": str(item),
            })
        elif item.suffix == ".py":
            summary.append({
                "name": item.name,
                "type": "Standalone Script",
                "status": "Pending Sanitization",
                "path": str(item),
            })

    return summary


def get_staged_skills_summary() -> List[Dict[str, str]]:
    """Data Provider: Inspects staged storage for TUI renderers."""
    if not PKG_STAGED_SKILLS_DIR.exists():
        return []

    staged_items = sorted(
        [p for p in PKG_STAGED_SKILLS_DIR.iterdir() if p.name != ".gitkeep"],
        key=lambda x: (not x.is_dir(), x.name),
    )

    summary = []
    for item in staged_items:
        if item.is_dir():
            has_manifest = (item / "manifest.json").exists()
            has_plugin = (item / "plugin.py").exists()

            if has_manifest and has_plugin:
                status = "STAGED"
            elif has_manifest:
                status = "Missing plugin.py"
            elif has_plugin:
                status = "Missing manifest.json"
            else:
                status = "Incomplete Package"

            summary.append({
                "name": item.name,
                "type": "Directory Package",
                "status": status,
                "path": str(item),
            })
        elif item.suffix == ".py":
            summary.append({
                "name": item.name,
                "type": "Standalone Script",
                "status": "Unmanifested",
                "path": str(item),
            })

    return summary


def run_ingest(
    source_path: Path,
    raw_category: Optional[str] = None,
    explicit_action: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Zero-Trust Ingestion Engine.
    Converts untrusted user/agent files into canonical packages, enforces directory
    structures (storage/staged/skill_<category>_<action>), updates DB record status
    to STAGED, and completely isolates agent assignment.
    """
    flag_quarantined_orphans()

    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        return False, f"Source path '{source_path}' does not exist."

    # 1. Parse Untrusted Manifest Input (If Exists)
    untrusted_manifest = {}
    manifest_src = source_path / "manifest.json" if source_path.is_dir() else None
    if manifest_src and manifest_src.exists():
        try:
            untrusted_manifest = json.loads(manifest_src.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 2. Enforce Canonical Naming Policy
    category = slugify(raw_category or untrusted_manifest.get("category") or "general")
    if not category:
        category = "general"

    supported_actions = untrusted_manifest.get("supported_actions", {})
    if explicit_action:
        action_name = slugify(explicit_action)
    elif isinstance(supported_actions, dict) and supported_actions:
        action_name = slugify(list(supported_actions.keys())[0])
    else:
        action_name = derive_action_name(source_path.stem)

    canonical_skill_id = f"skill_{category}_{action_name}"

    # Target directory is strictly absolute: storage/staged/skill_<category>_<action>
    target_dir = (PKG_STAGED_SKILLS_DIR / canonical_skill_id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    plugin_path = target_dir / "plugin.py"
    target_manifest_path = target_dir / "manifest.json"

    try:
        # 3. Defensive File Transfer
        if source_path.is_file():
            shutil.copy2(source_path, plugin_path)
        elif source_path.is_dir():
            for item in source_path.iterdir():
                dest_item = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest_item, dirs_exist_ok=True)
                elif item.name != "manifest.json":
                    shutil.copy2(item, dest_item)

            if not plugin_path.exists():
                py_files = [f for f in target_dir.glob("*.py") if f.name != "__init__.py"]
                if len(py_files) == 1:
                    py_files[0].rename(plugin_path)

        # Ensure entrypoint plugin exists
        if not plugin_path.exists():
            replacements = {
                "SKILL_ID": canonical_skill_id,
                "ACTION_NAME": action_name,
                "CATEGORY": category,
            }
            plugin_content = get_template_content("plugin.py", replacements)
            plugin_path.write_text(plugin_content, encoding="utf-8")

        # 4. AST Validation
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"AST Validation Error: {ast_err}"

        # 5. Manifest Reconstruction (Overwriting Untrusted Input)
        parameters = {}
        if isinstance(supported_actions, dict) and action_name in supported_actions:
            parameters = supported_actions[action_name].get("parameters", {})

        clean_manifest = {
            "skill_id": canonical_skill_id,
            "version": str(untrusted_manifest.get("version", "1.0.0")),
            "description": str(untrusted_manifest.get("description", f"Action handler for {action_name}")),
            "category": category,
            "author": str(untrusted_manifest.get("author", "Charon Librarian")),
            "shelf_tags": untrusted_manifest.get("shelf_tags", [action_name]),
            "allowed_agents": ["*"],
            "system_requirements": untrusted_manifest.get("system_requirements", []),
            "supported_actions": {
                action_name: {
                    "description": str(untrusted_manifest.get("description", f"Action handler for {action_name}")),
                    "parameters": parameters,
                }
            },
        }

        target_manifest_path.write_text(json.dumps(clean_manifest, indent=2), encoding="utf-8")

        # 6. Database Registration (Exact DDL Schema Alignment, Status 'STAGED')
        db_success, db_err = register_skill_in_db(
            skill_id=canonical_skill_id,
            action_name=action_name,
            version=clean_manifest["version"],
            category=category,
            description=clean_manifest["description"],
            parameters=parameters,
            system_requirements=clean_manifest["system_requirements"],
            consumed_artifacts=untrusted_manifest.get("consumed_artifacts", []),
            produced_artifacts=untrusted_manifest.get("produced_artifacts", []),
            entry_file_path=plugin_path,
            handler_name="execute_action",
            is_global=int(untrusted_manifest.get("is_global", 0)),
            status="STAGED",
        )

        if not db_success:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, db_err

        # 7. Safe Quarantine Cleanup (Only executed after validations and DB commit succeed)
        is_quarantined_src = (
            PKG_QUARANTINE_SKILLS_DIR.resolve() in source_path.parents
            or source_path.parent.resolve() == PKG_QUARANTINE_SKILLS_DIR.resolve()
            or source_path.resolve() == PKG_QUARANTINE_SKILLS_DIR.resolve()
        )
        if is_quarantined_src and source_path.exists():
            if source_path.is_file():
                source_path.unlink()
            else:
                shutil.rmtree(source_path, ignore_errors=True)

        return True, str(target_dir)

    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, f"Ingestion Failure: {str(e)}"


def run_quarantine_sanitizer() -> Dict[str, Any]:
    """
    Scans quarantine storage, applies AST checks, enforces canonical naming,
    and moves valid packages into staged storage and database STAGED status.
    """
    flag_quarantined_orphans()
    results: Dict[str, Any] = {"passed": [], "failed": [], "sync_code": 0}

    if not PKG_QUARANTINE_SKILLS_DIR.exists():
        return results

    items = [
        p for p in PKG_QUARANTINE_SKILLS_DIR.iterdir()
        if not p.name.startswith(".") and p.name != ".gitkeep"
    ]

    for item in items:
        success, msg_or_path = run_ingest(source_path=item)
        if success:
            results["passed"].append(item.name)
        else:
            report = {"item": item.name, "status": "REJECTED", "error": msg_or_path}
            if item.is_dir():
                (item / ".validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            results["failed"].append({"item": item.name, "error": msg_or_path})

    return results


def run_create(skill_id: str, category: str = "general") -> Tuple[bool, str]:
    """Scaffolds a skill directly in staged storage with status STAGED."""
    flag_quarantined_orphans()

    clean_category = slugify(category) or "general"
    action_name = derive_action_name(skill_id)
    canonical_skill_id = f"skill_{clean_category}_{action_name}"

    target_dir = PKG_STAGED_SKILLS_DIR / canonical_skill_id
    if target_dir.exists():
        return False, f"Skill ID '{canonical_skill_id}' already exists in staged storage."

    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        "SKILL_ID": canonical_skill_id,
        "ACTION_NAME": action_name,
        "CATEGORY": clean_category,
    }

    try:
        manifest_content = get_template_content("manifest.json", replacements)
        plugin_content = get_template_content("plugin.py", replacements)

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        manifest_path.write_text(manifest_content, encoding="utf-8")
        plugin_path.write_text(plugin_content, encoding="utf-8")

        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"AST Validation Error: {ast_err}"

        manifest_data = json.loads(manifest_content)

        db_success, db_err = register_skill_in_db(
            skill_id=canonical_skill_id,
            action_name=action_name,
            version=manifest_data.get("version", "1.0.0"),
            category=clean_category,
            description=manifest_data.get("description", ""),
            parameters={},
            system_requirements=[],
            consumed_artifacts=[],
            produced_artifacts=[],
            entry_file_path=plugin_path,
            handler_name="execute_action",
            status="STAGED",
        )

        if not db_success:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, db_err

        return True, str(target_dir)

    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, str(e)


def run_edit(skill_id: str) -> Tuple[bool, str]:
    """Headless editor launcher. Opens $EDITOR and validates on exit."""
    # 1. Resolve manifest location across staged and dynamic directories
    staged_manifest = PKG_STAGED_SKILLS_DIR / skill_id / "manifest.json"
    dynamic_manifest = PKG_DYNAMIC_SKILLS_DIR / skill_id / "manifest.json"
    direct_path = Path(skill_id)

    if direct_path.exists() and direct_path.name == "manifest.json":
        manifest_path = direct_path
    elif direct_path.is_dir() and (direct_path / "manifest.json").exists():
        manifest_path = direct_path / "manifest.json"
    elif staged_manifest.exists():
        manifest_path = staged_manifest
    elif dynamic_manifest.exists():
        manifest_path = dynamic_manifest
    else:
        return False, f"Could not locate manifest for skill '{skill_id}' in staged or dynamic storage."

    # 2. Launch external editor
    raw_editor = os.environ.get("EDITOR") or "nano"
    cmd = shlex.split(raw_editor) + [str(manifest_path)]

    try:
        subprocess.call(cmd)
    except FileNotFoundError:
        return False, f"Editor '{raw_editor}' not found. Please install it or set $EDITOR."
    except Exception as e:
        return False, f"Failed to launch editor: {str(e)}"

    # 3. Validate JSON integrity post-edit
    try:
        json.loads(manifest_path.read_text(encoding="utf-8"))
        return True, str(manifest_path)
    except Exception as e:
        return False, f"Manifest JSON invalid after edit: {str(e)}"