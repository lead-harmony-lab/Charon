"""
charon/cli/librarian/manifest.py
System Version: v0.3.0 | File Revision: 2.1.0

Module: Dynamic, schema-driven manifest validation, disk persistence, and auto-migration engine.
Leverages Pydantic SkillManifest model directly to eliminate hardcoded format constraints.
Refactored for multi-action unrolling, robust schema fallback, allowed_agents updates, and CLI diagnostics.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)
from charon.core.skills import SkillManifest

console = Console()
logger = logging.getLogger("charon.cli.librarian.manifest")


def update_manifest_allowed_agents(
    manifest_path: Union[str, Path],
    agents: List[str],
) -> bool:
    """
    Persists updated allowed_agents array to manifest.json on disk while
    preserving formatting and sorting deduplicated agent identifiers.
    """
    p = Path(manifest_path)
    if not p.exists():
        console.print(f"[bold red]❌ Manifest file not found at {manifest_path}[/bold red]")
        return False

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["allowed_agents"] = sorted(list(set(agents)))

        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return True
    except Exception as e:
        console.print(f"[bold red]❌ Failed to update manifest on disk: {e}[/bold red]")
        return False


def _migrate_raw_dict(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Dynamically converts legacy/deprecated dictionary keys to the current SkillManifest schema."""
    migrated = dict(raw)
    modified = False

    # Ensure required top-level defaults
    if "category" not in migrated or not migrated["category"]:
        migrated["category"] = "General"
        modified = True

    if "version" not in migrated or not migrated["version"]:
        migrated["version"] = "1.0.0"
        modified = True

    # Standardize actions / legacy keys into supported_actions mapping
    if "actions" in migrated and "supported_actions" not in migrated:
        actions = migrated.pop("actions")
        if isinstance(actions, dict):
            migrated["supported_actions"] = actions
            modified = True
        elif isinstance(actions, list):
            migrated["supported_actions"] = {
                act.get("name", f"action_{i}"): act
                for i, act in enumerate(actions)
                if isinstance(act, dict)
            }
            modified = True

    # Flatten single handler declarations into supported_actions mapping
    if "handler_name" in migrated and "supported_actions" not in migrated:
        handler = migrated.pop("handler_name")
        skill_id = migrated.get("skill_id", "default_action")
        migrated["supported_actions"] = {
            skill_id: {
                "handler_name": handler,
                "description": migrated.get(
                    "description", "Auto-migrated handler"
                ),
            }
        }
        modified = True

    # Standardize shorthand string actions into full canonical dictionaries
    if "supported_actions" in migrated and isinstance(migrated["supported_actions"], dict):
        for act_key, act_val in list(migrated["supported_actions"].items()):
            if isinstance(act_val, str):
                migrated["supported_actions"][act_key] = {
                    "description": act_val,
                    "parameters": {},
                }
                modified = True
            elif isinstance(act_val, dict):
                if "description" not in act_val or not act_val["description"]:
                    act_val["description"] = f"Execution action handler for {act_key}"
                    modified = True

    return migrated, modified


def validate_manifest_file(
    file_path: Path, auto_fix: bool = False
) -> Tuple[bool, List[str], bool]:
    """Validates a manifest against Pydantic SkillManifest schema and performs auto-migration if enabled."""
    if not file_path.exists():
        return False, [f"File not found: {file_path}"], False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        return False, [f"JSON Parse Error: {e}"], False

    if not isinstance(raw_data, dict):
        return False, ["Invalid manifest structure: root JSON must be an object"], False

    migrated_data, was_migrated = _migrate_raw_dict(raw_data)

    try:
        manifest = SkillManifest.model_validate(migrated_data)
        was_fixed = False

        if (was_migrated or auto_fix) and auto_fix:
            canonical_data = manifest.model_dump(exclude_none=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(canonical_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            was_fixed = True

        return True, [], was_fixed
    except ValidationError as ve:
        errors = [
            f"Field '{' -> '.join(str(x) for x in err['loc'])}': {err['msg']}"
            for err in ve.errors()
        ]
        return False, errors, False


def run_check(
    paths: Optional[List[Path]] = None, auto_fix: bool = False
) -> int:
    """Scans target paths and outputs a schema validation diagnostic report."""
    target_paths = paths or [
        PKG_DYNAMIC_SKILLS_DIR,
        PKG_STAGED_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]
    manifest_files: List[Path] = []

    for path in target_paths:
        if not path.exists():
            continue
        if path.is_file() and path.name == "manifest.json":
            manifest_files.append(path)
        elif path.is_dir():
            manifest_files.extend(path.rglob("manifest.json"))

    if not manifest_files:
        console.print(
            "[yellow]No `manifest.json` files discovered to check.[/yellow]"
        )
        return 0

    table = Table(title="Charon Skill Manifest Validation Report")
    table.add_column("Manifest Path", style="cyan", overflow="fold")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Category", style="magenta")
    table.add_column("Actions", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Notes / Errors", style="dim")

    total_invalid = 0
    for manifest_path in manifest_files:
        is_valid, errors, was_fixed = validate_manifest_file(
            manifest_path, auto_fix=auto_fix
        )
        try:
            rel_path = str(manifest_path.relative_to(Path.cwd()))
        except ValueError:
            rel_path = str(manifest_path.resolve())

        if is_valid:
            status_str = (
                "[bold green]FIXED[/bold green]"
                if was_fixed
                else "[bold green]VALID[/bold green]"
            )
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill_id = data.get("skill_id", "unknown")
                category = data.get("category", "General")
                actions_count = str(len(data.get("supported_actions", {})))
            except Exception:
                skill_id, category, actions_count = "unknown", "General", "?"

            note = "Migrated to canonical schema" if was_fixed else "OK"
            table.add_row(rel_path, skill_id, category, actions_count, status_str, note)
        else:
            total_invalid += 1
            table.add_row(
                rel_path,
                "-",
                "-",
                "0",
                "[bold red]INVALID[/bold red]",
                f"[red]{' | '.join(errors)}[/red]",
            )

    console.print(table)
    return 0 if total_invalid == 0 else 1