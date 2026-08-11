"""
charon/cli/librarian/lifecycle.py
System Version: v0.2.0 | File Revision: 2.1.0

Module: Skill lifecycle operations: promotion, demotion/quarantine, renaming, and purging.
Features strict isolation guards to prevent unintended directory deletion or database record wipes.
"""

import json
import logging
from pathlib import Path
import re
import shutil
from typing import List, Optional

from rich.console import Console

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

console = Console()
logger = logging.getLogger("charon.cli.librarian.lifecycle")


def _slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    if not text:
        return ""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def _cleanup_agent_mappings_for_skill(skill_id: str) -> None:
    """
    Purges corresponding bindings from agent_skill_map BEFORE database resync.

    SAFETY GUARANTEE: Uses explicit parameter binding scoped strictly to `skill_id`.
    Never executes global tables resets or un-parameterized DELETE statements.
    """
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            # Delete ONLY mappings for this explicit skill_id
            cursor.execute(
                "DELETE FROM agent_skill_map WHERE skill_id = ?",
                (skill_id,),
            )
            # Delete ONLY skill_registry record for this explicit skill_id
            cursor.execute(
                "DELETE FROM skill_registry WHERE skill_id = ?",
                (skill_id,),
            )
            conn.commit()
            logger.info(f"Purged database records scoped strictly to skill_id='{skill_id}'")
    except Exception as e:
        logger.warning(f"Failed to purge DB records for skill '{skill_id}': {e}")


def run_promote(skill_id: str) -> int:
    """Promotes a staged skill into active production dynamic status after schema validation."""
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Invalid skill_id provided.")
        return 1

    staged_manifest = find_skill_manifest(clean_id, stage_filter="Staged")
    if not staged_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Skill '{clean_id}' with stage='Staged' not found."
        )
        return 1

    # Pre-check schema validity before promoting
    is_valid, errors, _ = validate_manifest_file(staged_manifest, auto_fix=True)
    if not is_valid:
        console.print(
            "[bold red]❌ Cannot promote invalid skill manifest:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    staged_dir = staged_manifest.parent
    target_dir = PKG_DYNAMIC_SKILLS_DIR / staged_dir.name

    existing_dynamic_manifest = find_skill_manifest(
        clean_id, stage_filter="Dynamic"
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
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

    shutil.rmtree(staged_dir)

    # Clean up redundant dynamic dir if target moved locations
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
        f"[bold green]✅ Promoted[/bold green] skill '[bold white]{clean_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_demote(skill_id: str) -> int:
    """Demotes/quarantines a dynamic skill back to staged status for debugging."""
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Invalid skill_id provided.")
        return 1

    dynamic_manifest = find_skill_manifest(clean_id, stage_filter="Dynamic")
    if not dynamic_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Active dynamic skill '{clean_id}' not found."
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
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

    console.print(
        f"[bold yellow]⚠️ Demoted[/bold yellow] skill '[bold white]{clean_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_rename(old_skill_id: str, new_skill_id: str) -> int:
    """Renames a skill_id inside its manifest, updates folder structure, and syncs SQLite indexing."""
    clean_old_id = _slugify(old_skill_id)
    clean_new_id = _slugify(new_skill_id)

    if not clean_old_id or not clean_new_id:
        console.print("[bold red]Error:[/bold red] Source and target skill IDs must be non-empty.")
        return 1

    manifest_path = find_skill_manifest(clean_old_id)
    if not manifest_path:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate skill '{clean_old_id}'."
        )
        return 1

    skill_dir = manifest_path.parent
    target_dir = skill_dir.parent / clean_new_id

    # COLLISION GUARD: Prevent overwriting an existing non-target folder
    if target_dir.exists() and target_dir.resolve() != skill_dir.resolve():
        console.print(
            f"[bold red]Error:[/bold red] Target directory already exists: {target_dir}"
        )
        return 1

    # In-place manifest update for skill_id
    with open(manifest_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data["skill_id"] = clean_new_id
        f.seek(0)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.truncate()
        f.write("\n")

    if skill_dir.name != clean_new_id:
        skill_dir.rename(target_dir)
        console.print(
            f"[dim]Renamed skill folder {skill_dir} -> {target_dir}[/dim]"
        )

    # Scoped database cleanup for old ID to avoid orphaned DB records
    _cleanup_agent_mappings_for_skill(clean_old_id)

    console.print(
        f"[bold green]✅ Renamed[/bold green] '{clean_old_id}' -> '[bold cyan]{clean_new_id}[/bold cyan]'."
    )
    return run_sync()


def run_delete_skill(skill_id: str) -> int:
    """
    Purges directory instances of a specific skill and cleans corresponding SQLite records.

    SAFETY ISOLATION GUARANTEES:
      1. Requires explicit non-empty skill_id (prevents empty/wildcard matching).
      2. Validates child subfolder depth to prevent wiping root skill directories.
      3. Scopes DB removal queries strictly to the target skill_id.
    """
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Cannot execute deletion with an empty or invalid skill_id.")
        return 1

    search_roots = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    # Protected root directories that must NEVER be deleted
    protected_roots = {r.resolve() for r in search_roots if r.exists()}
    protected_roots.update({Path.home().resolve(), Path.cwd().resolve(), Path("/").resolve()})

    deleted_paths: List[Path] = []

    for root in search_roots:
        if not root.exists():
            continue

        for manifest_path in list(root.rglob("manifest.json")):
            skill_dir = manifest_path.parent.resolve()

            # SAFETY GUARD 1: Absolute protection against wiping root container directories
            if skill_dir in protected_roots:
                logger.warning(
                    f"Skipping deletion at {manifest_path}: Manifest is located directly in root directory {skill_dir}."
                )
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                manifest_id = data.get("skill_id")

                # SAFETY GUARD 2: Explicit equality match on skill_id
                if manifest_id == clean_id or manifest_id == skill_id:
                    if skill_dir.exists():
                        shutil.rmtree(skill_dir)
                        deleted_paths.append(skill_dir)
            except Exception as e:
                logger.error(f"Error inspecting manifest at {manifest_path}: {e}")

    if not deleted_paths:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate any skill folder matching '{clean_id}'."
        )
        return 1

    # SAFETY GUARD 3: Targeted DB cleanup scoped only to target skill_id
    _cleanup_agent_mappings_for_skill(clean_id)

    for p in deleted_paths:
        console.print(f"[bold yellow]🗑️ Purged directory:[/bold yellow] {p}")

    console.print(
        f"[bold green]✅ Successfully deleted skill '[bold cyan]{clean_id}[/bold cyan]'.[/bold green]"
    )
    return run_sync()