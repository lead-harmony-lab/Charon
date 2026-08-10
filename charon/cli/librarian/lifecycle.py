"""
charon/cli/librarian/lifecycle.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Skill lifecycle operations: promotion, demotion/quarantine, renaming, and purging.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional
from rich.console import Console

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)
from charon.cli.librarian.database import run_sync
from charon.cli.librarian.permissions import find_skill_manifest

console = Console()
logger = logging.getLogger("charon.cli.librarian.lifecycle")


def run_promote(skill_id: str) -> int:
    """Promotes a staged skill into active production dynamic status."""
    staged_manifest = find_skill_manifest(skill_id, stage_filter="Staged")
    if not staged_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Skill '{skill_id}' with stage='Staged' not found."
        )
        return 1

    staged_dir = staged_manifest.parent
    target_dir = PKG_DYNAMIC_SKILLS_DIR / staged_dir.name

    existing_dynamic_manifest = find_skill_manifest(
        skill_id, stage_filter="Dynamic"
    )
    old_dynamic_dir: Optional[Path] = (
        existing_dynamic_manifest.parent
        if existing_dynamic_manifest
        else None
    )

    shutil.copytree(staged_dir, target_dir, dirs_exist_ok=True)

    target_manifest = target_dir / "manifest.json"
    if target_manifest.exists():
        with open(target_manifest, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["stage"] = "Dynamic"
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

    shutil.rmtree(staged_dir)

    if (
        old_dynamic_dir
        and old_dynamic_dir.exists()
        and old_dynamic_dir.resolve() != target_dir.resolve()
    ):
        shutil.rmtree(old_dynamic_dir)
        console.print(
            f"[dim]Cleaned up redundant dynamic directory: {old_dynamic_dir}[/dim]"
        )

    console.print(
        f"[bold green]✅ Promoted[/bold green] skill '[bold white]{skill_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_demote(skill_id: str) -> int:
    """Demotes/quarantines a dynamic skill back to staged status for debugging."""
    dynamic_manifest = find_skill_manifest(skill_id, stage_filter="Dynamic")
    if not dynamic_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Active dynamic skill '{skill_id}' not found."
        )
        return 1

    dynamic_dir = dynamic_manifest.parent
    target_dir = PKG_STAGED_SKILLS_DIR / dynamic_dir.name

    shutil.copytree(dynamic_dir, target_dir, dirs_exist_ok=True)
    shutil.rmtree(dynamic_dir)

    staged_manifest = target_dir / "manifest.json"
    if staged_manifest.exists():
        with open(staged_manifest, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["stage"] = "Staged"
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

    console.print(
        f"[bold yellow]⚠️ Demoted[/bold yellow] skill '[bold white]{skill_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_rename(old_skill_id: str, new_skill_id: str) -> int:
    """Renames a skill_id inside its manifest, updates folder structure, and updates SQLite indexing."""
    manifest_path = find_skill_manifest(old_skill_id)
    if not manifest_path:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate skill '{old_skill_id}'."
        )
        return 1

    with open(manifest_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data["skill_id"] = new_skill_id
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()

    skill_dir = manifest_path.parent
    if skill_dir.name == old_skill_id:
        target_dir = skill_dir.parent / new_skill_id
        if not target_dir.exists():
            skill_dir.rename(target_dir)
            console.print(
                f"[dim]Renamed skill folder {skill_dir} -> {target_dir}[/dim]"
            )

    console.print(
        f"[bold green]✅ Renamed[/bold green] '{old_skill_id}' -> '[bold cyan]{new_skill_id}[/bold cyan]'."
    )
    return run_sync()


def run_delete_skill(skill_id: str) -> int:
    """Purges all directory instances of a skill and cleans SQLite registry."""
    search_dirs = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]
    deleted_paths: List[Path] = []

    for root in search_dirs:
        if not root.exists():
            continue
        for manifest_path in list(root.rglob("manifest.json")):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("skill_id") == skill_id:
                    skill_dir = manifest_path.parent
                    if skill_dir.exists():
                        shutil.rmtree(skill_dir)
                        deleted_paths.append(skill_dir)
            except Exception as e:
                logger.error(
                    f"Error inspecting manifest at {manifest_path}: {e}"
                )

    if not deleted_paths:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate any skill folder for '{skill_id}'."
        )
        return 1

    for p in deleted_paths:
        console.print(f"[bold yellow]🗑️ Purged directory:[/bold yellow] {p}")

    console.print(
        f"[bold green]✅ Successfully deleted skill '[bold cyan]{skill_id}[/bold cyan]'.[/bold green]"
    )
    return run_sync()