"""
charon/cli/librarian/manifest.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Dynamic, schema-driven manifest validation and auto-migration engine.
Leverages Pydantic SkillManifest model directly to eliminate hardcoded format constraints.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _migrate_raw_dict(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Dynamically converts legacy/deprecated dictionary keys to the current SkillManifest schema."""
    migrated = dict(raw)
    modified = False

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

    migrated_data, was_migrated = _migrate_raw_dict(raw_data)

    try:
        manifest = SkillManifest.model_validate(migrated_data)
        was_fixed = False

        if (was_migrated or auto_fix) and auto_fix:
            canonical_data = manifest.model_dump(exclude_none=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(canonical_data, f, indent=2)
            was_fixed = True

        return True, [], was_fixed
    except ValidationError as ve:
        errors = [
            f"[{' -> '.join(str(x) for x in err['loc'])}]: {err['msg']}"
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
    table.add_column("Actions", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Notes / Errors", style="dim")

    total_invalid = 0
    for manifest_path in manifest_files:
        is_valid, errors, was_fixed = validate_manifest_file(
            manifest_path, auto_fix=auto_fix
        )
        rel_path = str(manifest_path.resolve())
        try:
            rel_path = str(manifest_path.relative_to(Path.cwd()))
        except ValueError:
            pass

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
                actions_count = str(len(data.get("supported_actions", {})))
            except Exception:
                skill_id, actions_count = "unknown", "?"

            note = "Migrated to canonical schema" if was_fixed else "OK"
            table.add_row(rel_path, skill_id, actions_count, status_str, note)
        else:
            total_invalid += 1
            table.add_row(
                rel_path,
                "-",
                "0",
                "[bold red]INVALID[/bold red]",
                f"[red]{' | '.join(errors)}[/red]",
            )

    console.print(table)
    return 0 if total_invalid == 0 else 1