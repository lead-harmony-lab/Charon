"""
charon/cli/librarian/ingestion.py
System Version: v0.2.0 | File Revision: 2.8.2

Module: Core headless engine for dynamic skill creation, quarantine sanitization,
and file ingestion. Completely decoupled from Rich console rendering and interactive prompts
so all UI rendering can be handled by TUI/CLI view layers.
"""

import ast
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest, get_registered_agents
from charon.cli.librarian.service import register_and_bind_skill
from charon.config.paths import (
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_QUARANTINE_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

# -----------------------------------------------------------------------------
# Module Exports / Path Aliases (Backward & UI Compatibility)
# -----------------------------------------------------------------------------
SKILLS_QUARANTINE_DIR = PKG_QUARANTINE_SKILLS_DIR
SKILLS_STAGED_DIR = PKG_STAGED_SKILLS_DIR
SKILLS_DYNAMIC_DIR = PKG_DYNAMIC_SKILLS_DIR

SKILLS_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "skills" / "templates"
)


def slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def derive_action_name(skill_id: str) -> str:
    """
    Derives a standard action_name from skill_id to prevent name collision bugs.
    Example: 'planner_synthesize' -> 'synthesize'
             'code_executor'     -> 'execute'
    """
    parts = skill_id.split("_")
    if len(parts) > 1:
        suffix = parts[-1]
        verb_map = {
            "executor": "execute",
            "generator": "generate",
            "evaluator": "evaluate",
            "analyzer": "analyze",
            "builder": "build",
        }
        return verb_map.get(suffix, suffix)
    return skill_id if skill_id else "run"


def validate_target_agent(target_agent: Optional[str]) -> Tuple[bool, str]:
    """
    Verifies whether a specified agent identifier exists in the agent registry.
    Returns (is_valid, error_message).
    """
    if not target_agent:
        return True, ""

    registered_agents = get_registered_agents()
    if target_agent not in registered_agents:
        available_str = ", ".join(registered_agents) if registered_agents else "None"
        return False, f"Agent '{target_agent}' is not registered. Available agents: {available_str}"

    return True, ""


def flag_quarantined_orphans() -> int:
    """
    Scans skill_registry for records whose entry_file_path no longer exists
    on disk and marks their status as 'QUARANTINED' with an explicit reason
    rather than deleting them from the database.
    Returns the count of newly flagged skills.
    """
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT skill_id, entry_file_path, status FROM skill_registry")
            rows = cursor.fetchall()

            flagged_count = 0
            for sid, entry_path_str, status in rows:
                if entry_path_str:
                    entry_path = Path(entry_path_str)
                    if not entry_path.exists() and status != "QUARANTINED":
                        cursor.execute(
                            """
                            UPDATE skill_registry
                            SET status = 'QUARANTINED',
                                quarantine_reason = 'MISSING_ENTRY_FILE: Path on disk not found',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE skill_id = ?
                            """,
                            (sid,),
                        )
                        flagged_count += 1

        return flagged_count
    except Exception as e:
        print(f"Warning: Failed to flag quarantine orphans in SQLite: {e}")
        return 0


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
                "path": str(item)
            })
        elif item.suffix == ".py":
            summary.append({
                "name": item.name,
                "type": "Standalone Script",
                "status": "Pending Sanitization",
                "path": str(item)
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
                status = "Ready to Bind"
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
                "path": str(item)
            })
        elif item.suffix == ".py":
            summary.append({
                "name": item.name,
                "type": "Standalone Script",
                "status": "Unmanifested",
                "path": str(item)
            })

    return summary


def is_skill_id_taken(skill_id: str, ignore_path: Optional[Path] = None) -> bool:
    """Checks if a skill identifier already exists in staged or dynamic storage."""
    staged_path = PKG_STAGED_SKILLS_DIR / skill_id
    dynamic_path = PKG_DYNAMIC_SKILLS_DIR / skill_id
    quarantine_path = PKG_QUARANTINE_SKILLS_DIR / skill_id

    if ignore_path and quarantine_path.resolve() == ignore_path.resolve():
        return staged_path.exists() or dynamic_path.exists()

    return quarantine_path.exists() or staged_path.exists() or dynamic_path.exists()


def get_template_content(filename: str, replacements: Optional[dict] = None) -> str:
    """Reads a template file from charon/skills/templates and replaces double-curly placeholders."""
    template_path = SKILLS_TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Required template file missing at: {template_path}")

    content = template_path.read_text(encoding="utf-8")
    if replacements:
        for key, value in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def verify_plugin_entrypoint(plugin_path: Path) -> Tuple[bool, str]:
    """Uses AST parsing to verify that plugin.py is syntactically valid and exposes a handler."""
    if not plugin_path.exists():
        return False, f"Plugin file missing at: {plugin_path}"

    try:
        tree = ast.parse(plugin_path.read_text(encoding="utf-8"), filename=str(plugin_path))
        declared_functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        if "execute_action" not in declared_functions and not any(
            f.startswith("handle_") or f != "run" for f in declared_functions
        ) and not declared_functions:
            return (
                False,
                "Plugin must define 'execute_action' router or at least one function handler.",
            )

        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in plugin file '{plugin_path.name}': {e}"


def run_quarantine_sanitizer(target_agent: Optional[str] = None) -> Dict[str, Any]:
    """
    Headless Deterministic Sanitizer Pipeline.
    Scans storage/quarantine/, performs AST checks, cleans folder artifacts,
    validates manifest schema, and promotes valid skills to storage/staged/.
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
        errors = []
        sid = slugify(item.stem if item.is_file() else item.name)
        action_name = derive_action_name(sid)
        staged_target = PKG_STAGED_SKILLS_DIR / sid

        if staged_target.exists():
            errors.append(f"Skill ID '{sid}' already exists in staged storage.")

        if not errors:
            # Wrap standalone script into package structure
            if item.is_file() and item.suffix == ".py":
                temp_pkg = PKG_QUARANTINE_SKILLS_DIR / f"_temp_{sid}"
                temp_pkg.mkdir(exist_ok=True)
                shutil.move(str(item), str(temp_pkg / "plugin.py"))

                replacements = {
                    "SKILL_ID": sid,
                    "ACTION_NAME": action_name,
                    "CATEGORY": "Quarantine-Ingested",
                }
                manifest_content = get_template_content("manifest.json", replacements)
                (temp_pkg / "manifest.json").write_text(manifest_content, encoding="utf-8")

                pkg_dir = PKG_QUARANTINE_SKILLS_DIR / sid
                if pkg_dir.exists():
                    shutil.rmtree(pkg_dir)
                temp_pkg.rename(pkg_dir)
                item = pkg_dir

            if item.is_dir():
                # Gate 1: Artifact Cleanup
                for cache in item.rglob("__pycache__"):
                    shutil.rmtree(cache, ignore_errors=True)
                for ds_store in item.rglob(".DS_Store"):
                    ds_store.unlink(missing_ok=True)

                plugin_path = item / "plugin.py"
                if not plugin_path.exists():
                    py_files = [f for f in item.glob("*.py") if f.name != "__init__.py"]
                    if len(py_files) == 1:
                        py_files[0].rename(plugin_path)
                    elif not py_files:
                        replacements = {
                            "SKILL_ID": sid,
                            "ACTION_NAME": action_name,
                            "CATEGORY": "Quarantine-Ingested",
                        }
                        plugin_content = get_template_content("plugin.py", replacements)
                        plugin_path.write_text(plugin_content, encoding="utf-8")

                # Gate 2: AST Syntax Validation
                for py_file in item.rglob("*.py"):
                    try:
                        ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                    except SyntaxError as e:
                        errors.append(f"Syntax error in {py_file.name}: {e.msg} (line {e.lineno})")

                # Gate 3: Plugin Router Check
                if plugin_path.exists():
                    valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
                    if not valid_ast:
                        errors.append(f"Plugin Entrypoint Error: {ast_err}")

                # Gate 4: Manifest Verification & Action Naming Fix
                manifest_path = item / "manifest.json"
                if not manifest_path.exists():
                    replacements = {
                        "SKILL_ID": sid,
                        "ACTION_NAME": action_name,
                        "CATEGORY": "Quarantine-Ingested",
                    }
                    manifest_content = get_template_content("manifest.json", replacements)
                    manifest_path.write_text(manifest_content, encoding="utf-8")
                else:
                    try:
                        mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                        mdata["skill_id"] = sid
                        if "actions" in mdata and isinstance(mdata["actions"], list) and mdata["actions"]:
                            if mdata["actions"][0].get("name") == sid:
                                mdata["actions"][0]["name"] = action_name
                        manifest_path.write_text(json.dumps(mdata, indent=2), encoding="utf-8")
                    except Exception:
                        pass

                is_valid_manifest, manifest_errs, _ = validate_manifest_file(manifest_path, auto_fix=True)
                if not is_valid_manifest:
                    errors.extend(manifest_errs)

        if errors:
            report = {"skill_id": sid, "status": "REJECTED", "errors": errors}
            if item.is_dir():
                (item / ".validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            results["failed"].append({"skill_id": sid, "errors": errors})
        else:
            try:
                shutil.move(str(item), str(staged_target))
                manifest_data = json.loads((staged_target / "manifest.json").read_text(encoding="utf-8"))

                register_and_bind_skill(
                    skill_manifest=manifest_data,
                    entry_file_path=staged_target / "plugin.py",
                    target_agent_id=target_agent,
                )
                results["passed"].append(sid)
            except Exception as e:
                results["failed"].append({"skill_id": sid, "errors": [str(e)]})

    results["sync_code"] = run_sync()
    return results


def run_create(
    skill_id: str,
    category: str = "General",
    target_agent: Optional[str] = None
) -> Tuple[bool, str]:
    """Headless skill scaffolding engine. Returns (success_bool, message_or_path)."""
    flag_quarantined_orphans()

    is_valid_agent, agent_err = validate_target_agent(target_agent)
    if not is_valid_agent:
        return False, agent_err

    clean_skill_id = slugify(skill_id)
    action_name = derive_action_name(clean_skill_id)

    if is_skill_id_taken(clean_skill_id):
        return False, f"Skill ID '{clean_skill_id}' already exists in storage."

    target_dir = PKG_STAGED_SKILLS_DIR / clean_skill_id
    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        "SKILL_ID": clean_skill_id,
        "ACTION_NAME": action_name,
        "CATEGORY": category,
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

        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        run_sync()
        return True, str(target_dir)

    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, str(e)


def run_ingest(
    source_path: Path,
    skill_id: Optional[str] = None,
    target_agent: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Headless skill ingestion engine. Accepts explicit source_path and optional skill_id.
    Ensures physical file relocation out of quarantine and transactional database registration.
    """
    flag_quarantined_orphans()

    is_valid_agent, agent_err = validate_target_agent(target_agent)
    if not is_valid_agent:
        return False, agent_err

    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        return False, f"Source path '{source_path}' does not exist."

    # Fallback to file or directory name if skill_id is not explicitly provided
    effective_id = skill_id or source_path.stem
    sid = slugify(effective_id)
    action_name = derive_action_name(sid)

    if is_skill_id_taken(sid, ignore_path=source_path):
        return False, f"Skill ID '{sid}' is already taken in staged or dynamic storage."

    target_dir = PKG_STAGED_SKILLS_DIR / sid
    target_dir.mkdir(parents=True, exist_ok=True)

    is_quarantined_src = (
        PKG_QUARANTINE_SKILLS_DIR.resolve() in source_path.parents
        or source_path.parent.resolve() == PKG_QUARANTINE_SKILLS_DIR.resolve()
        or source_path.resolve() == (PKG_QUARANTINE_SKILLS_DIR / sid).resolve()
    )

    replacements = {
        "SKILL_ID": sid,
        "ACTION_NAME": action_name,
        "CATEGORY": "Ingested",
    }

    try:
        # 1. File Transfer & Quarantine Cleanup
        if source_path.is_file():
            shutil.copy2(source_path, target_dir / "plugin.py")
            if not (target_dir / "manifest.json").exists():
                manifest_content = get_template_content("manifest.json", replacements)
                (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

            if is_quarantined_src:
                source_path.unlink()

        elif source_path.is_dir():
            for item in source_path.iterdir():
                dest_item = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest_item)

            if not (target_dir / "plugin.py").exists():
                py_files = [f for f in target_dir.glob("*.py") if f.name != "__init__.py"]
                if len(py_files) == 1:
                    py_files[0].rename(target_dir / "plugin.py")
                elif not py_files:
                    plugin_content = get_template_content("plugin.py", replacements)
                    (target_dir / "plugin.py").write_text(plugin_content, encoding="utf-8")

            if not (target_dir / "manifest.json").exists():
                manifest_content = get_template_content("manifest.json", replacements)
                (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

            if is_quarantined_src:
                shutil.rmtree(source_path)

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        # 2. Manifest Schema Normalization
        if manifest_path.exists():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                mdata["skill_id"] = sid
                if "actions" in mdata and isinstance(mdata["actions"], list) and mdata["actions"]:
                    if mdata["actions"][0].get("name") == sid:
                        mdata["actions"][0]["name"] = action_name
                manifest_path.write_text(json.dumps(mdata, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError):
                pass

        # 3. Validations
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"AST Validation Error: {ast_err}"

        is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
        if not is_valid:
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"Manifest validation errors: {', '.join(errors)}"

        # 4. Service Registration & Database Binding
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        run_sync()
        return True, str(target_dir)

    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, str(e)


def run_edit(skill_id: str) -> Tuple[bool, str]:
    """Headless editor launcher. Opens $EDITOR and validates on exit."""
    manifest_path = find_skill_manifest(skill_id)
    if not manifest_path:
        return False, f"Could not locate skill '{skill_id}'."

    raw_editor = os.environ.get("EDITOR", "nano")
    cmd = shlex.split(raw_editor) + [str(manifest_path)]

    subprocess.call(cmd)

    is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
    if not is_valid:
        return False, f"Manifest validation failed after edit: {', '.join(errors)}"

    run_sync()
    return True, str(manifest_path)