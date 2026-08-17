"""
System Version: v2.0.0 | File Revision: 2.6.0

Module: Skill lifecycle operations: promotion, demotion/quarantine, renaming, default action binding, and purging.
Features strict isolation guards to prevent unintended directory deletion or database record wipes.
"""

import json
import logging
from pathlib import Path
import re
import shutil
from typing import List, Optional

from rich.console import Console

from charon.cli.librarian.db import (
    get_skill_entry_and_status,
    migrate_skill_id_in_db,
    purge_skill_records,
    run_sync,
    update_agent_default_action,
)
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.validators import verify_system_dependencies
from charon.config.paths import (
    AGENT_REGISTRY_JSON,
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)

console = Console()
logger = logging.getLogger("charon.cli.librarian.lifecycle")


def _slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    if not text:
        return ""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def _locate_skill_manifest(
    skill_id: str, stage_filter: Optional[str] = None
) -> Optional[Path]:
    """Locates manifest.json for a given skill_id or package name by querying database entry paths
    or scanning physical storage directories.
    """
    rows = get_skill_entry_and_status(skill_id)
    for entry_path_str, status_val in rows:
        if not entry_path_str:
            continue
        entry_path = Path(entry_path_str)
        manifest_path = entry_path.parent / "manifest.json"
        if manifest_path.exists():
            if not stage_filter:
                return manifest_path

            sf = stage_filter.upper()
            status_str = (status_val or "").upper()
            path_str = str(manifest_path).lower()

            if sf == "STAGED" and (
                status_str == "STAGED" or "/staged/" in path_str
            ):
                return manifest_path
            elif sf == "DYNAMIC" and (
                status_str in ("DYNAMIC", "USER DYNAMIC")
                or "/dynamic/" in path_str
            ):
                return manifest_path

    search_roots = []
    if stage_filter:
        sf = stage_filter.upper()
        if sf == "STAGED":
            search_roots = [PKG_STAGED_SKILLS_DIR]
        elif sf == "DYNAMIC":
            search_roots = [PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR]
    else:
        search_roots = [
            PKG_STAGED_SKILLS_DIR,
            PKG_DYNAMIC_SKILLS_DIR,
            DYNAMIC_SKILLS_DIR,
        ]

    target_id = skill_id.lower()
    clean_target = _slugify(skill_id).lower()

    for root in search_roots:
        if not root.exists():
            continue
        for m_path in root.rglob("manifest.json"):
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                pkg = (data.get("package") or data.get("skill_id") or "").lower()
                folder_name = m_path.parent.name.lower()

                action_ids = [
                    a.get("skill_id", "").lower()
                    for a in data.get("actions", [])
                    if isinstance(a, dict)
                ]

                if (
                    pkg in (target_id, clean_target)
                    or folder_name in (target_id, clean_target)
                    or target_id in action_ids
                    or clean_target in action_ids
                ):
                    if not stage_filter:
                        return m_path

                    sf = stage_filter.upper()
                    m_status = (data.get("status") or "").upper()
                    path_str = str(m_path).lower()

                    if sf == "STAGED" and (
                        m_status == "STAGED" or "/staged/" in path_str
                    ):
                        return m_path
                    elif sf == "DYNAMIC" and (
                        m_status in ("ACTIVE", "DYNAMIC", "USER DYNAMIC")
                        or "/dynamic/" in path_str
                    ):
                        return m_path
            except Exception:
                continue

    return None


def _clear_agent_default_actions_for_skill(action_name: str) -> None:
    """Clears matching default_action references in agent_registry.json on disk."""
    if not AGENT_REGISTRY_JSON.exists():
        return
    try:
        raw_text = AGENT_REGISTRY_JSON.read_text(encoding="utf-8")
        registry = json.loads(raw_text)
        modified = False

        for agent in registry:
            if agent.get("default_action") == action_name:
                agent["default_action"] = None
                modified = True

        if modified:
            temp_file = AGENT_REGISTRY_JSON.with_suffix(".tmp")
            temp_file.write_text(
                json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temp_file.replace(AGENT_REGISTRY_JSON)
    except Exception as e:
        logger.error(f"Error purging default actions from agent_registry.json: {e}")


def _cleanup_agent_mappings_for_skill(skill_id: str) -> None:
    """Purges corresponding bindings from DB records and disk configs BEFORE sync."""
    purge_skill_records(skill_id)
    _clear_agent_default_actions_for_skill(skill_id)


def run_set_agent_default_action(agent_id: str, action_name: Optional[str]) -> int:
    """Binds or unbinds an agent's default_action in SQLite and persists to agent_registry.json."""
    if not AGENT_REGISTRY_JSON.exists():
        console.print(
            f"[bold red]Error:[/bold red] Declarative registry file missing at '{AGENT_REGISTRY_JSON}'."
        )
        return 1

    try:
        # 1. Update SQLite Fastpath
        update_agent_default_action(agent_id, action_name)

        # 2. Update agent_registry.json
        raw_text = AGENT_REGISTRY_JSON.read_text(encoding="utf-8")
        registry = json.loads(raw_text)

        agent_found = False
        for record in registry:
            if record.get("agent_id") == agent_id:
                record["default_action"] = action_name
                agent_found = True
                break

        if not agent_found:
            console.print(
                f"[bold red]Error:[/bold red] Agent '{agent_id}' not found in '{AGENT_REGISTRY_JSON.name}'."
            )
            return 1

        # 3. Atomic Replacement
        temp_file = AGENT_REGISTRY_JSON.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp_file.replace(AGENT_REGISTRY_JSON)

        target_str = f"'{action_name}'" if action_name else "None"
        console.print(
            f"[bold green]✅ Updated[/bold green] Agent '[bold white]{agent_id}[/bold white]' "
            f"default_action -> [cyan]{target_str}[/cyan] (DB & agent_registry.json)"
        )
        return run_sync()
    except Exception as e:
        logger.error(f"Failed to assign default action for agent '{agent_id}': {e}")
        console.print(f"[bold red]❌ Failed to update agent default action:[/bold red] {e}")
        return 1


def run_promote(skill_id: str) -> int:
    """Promotes a staged skill into active production dynamic status.
    Acts as a strict gateway. Validates schema and dependencies without mutating manifest permissions.
    """
    staged_manifest = _locate_skill_manifest(skill_id, stage_filter="Staged")
    if not staged_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Skill '{skill_id}' in staged directory / status='STAGED' not found."
        )
        return 1

    is_valid, errors, _ = validate_manifest_file(staged_manifest, auto_fix=False)
    if not is_valid:
        console.print(
            "[bold red]❌ Cannot promote invalid skill manifest:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    with open(staged_manifest, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    requirements = manifest_data.get("system_requirements", [])
    deps_ok, missing_deps = verify_system_dependencies(requirements)

    if not deps_ok:
        console.print(
            f"[bold red]❌ Cannot promote '{skill_id}': Missing system dependencies.[/bold red]\n"
            f"[yellow]The environment is missing required binaries or packages: {', '.join(missing_deps)}[/yellow]"
        )
        return 1

    staged_dir = staged_manifest.parent
    target_dir = PKG_DYNAMIC_SKILLS_DIR / staged_dir.name

    existing_dynamic_manifest = _locate_skill_manifest(
        skill_id, stage_filter="Dynamic"
    )
    old_dynamic_dir: Optional[Path] = (
        existing_dynamic_manifest.parent if existing_dynamic_manifest else None
    )

    shutil.copytree(staged_dir, target_dir, dirs_exist_ok=True)

    target_manifest = target_dir / "manifest.json"
    if target_manifest.exists():
        with open(target_manifest, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["status"] = "ACTIVE"
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

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
    dynamic_manifest = _locate_skill_manifest(skill_id, stage_filter="Dynamic")
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
            data["status"] = "QUARANTINED"
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

    console.print(
        f"[bold yellow]⚠️ Demoted[/bold yellow] skill '[bold white]{skill_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_rename(old_skill_id: str, new_skill_id: str) -> int:
    """Renames a skill package or skill_id in actions[], updates folder structure, and migrates DB records."""
    clean_old_id = _slugify(old_skill_id)
    clean_new_id = _slugify(new_skill_id)

    if not clean_old_id or not clean_new_id:
        console.print(
            "[bold red]Error:[/bold red] Source and target skill IDs must be non-empty."
        )
        return 1

    manifest_path = _locate_skill_manifest(old_skill_id)
    if not manifest_path:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate skill package or action matching '{old_skill_id}'."
        )
        return 1

    skill_dir = manifest_path.parent
    target_dir = skill_dir.parent / clean_new_id

    if target_dir.exists() and target_dir.resolve() != skill_dir.resolve():
        console.print(
            f"[bold red]Error:[/bold red] Target directory already exists: {target_dir}"
        )
        return 1

    with open(manifest_path, "r+", encoding="utf-8") as f:
        data = json.load(f)

        if data.get("package") in (old_skill_id, clean_old_id):
            data["package"] = clean_new_id

        if "actions" in data and isinstance(data["actions"], list):
            for action in data["actions"]:
                if action.get("skill_id") in (old_skill_id, clean_old_id):
                    action["skill_id"] = clean_new_id
                if action.get("action_name") in (old_skill_id, clean_old_id):
                    action["action_name"] = clean_new_id

        f.seek(0)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.truncate()
        f.write("\n")

    if skill_dir.name in (old_skill_id, clean_old_id) and skill_dir.name != clean_new_id:
        skill_dir.rename(target_dir)
        console.print(f"[dim]Renamed skill folder {skill_dir} -> {target_dir}[/dim]")

    success, msg = migrate_skill_id_in_db(old_skill_id, clean_new_id)
    if not success:
        success, msg = migrate_skill_id_in_db(clean_old_id, clean_new_id)

    if not success:
        console.print(f"[bold red]❌ Database Migration Failed:[/bold red] {msg}")
        return 1

    console.print(
        f"[bold green]✅ Renamed[/bold green] '{old_skill_id}' -> '[bold cyan]{clean_new_id}[/bold cyan]' in DB & Filesystem."
    )
    return run_sync()


def run_delete_skill(skill_id: str) -> int:
    """Purges directory instances of a specific skill package and cleans corresponding SQLite records."""
    clean_id = _slugify(skill_id)
    if not clean_id and not skill_id:
        console.print(
            "[bold red]Error:[/bold red] Cannot execute deletion with an empty or invalid skill_id."
        )
        return 1

    manifest_path = _locate_skill_manifest(skill_id)

    search_roots = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    protected_roots = {r.resolve() for r in search_roots if r.exists()}
    protected_roots.update(
        {Path.home().resolve(), Path.cwd().resolve(), Path("/").resolve()}
    )

    dirs_to_delete = set()
    if manifest_path:
        dirs_to_delete.add(manifest_path.parent.resolve())

    for root in search_roots:
        if not root.exists():
            continue

        for m_file in root.rglob("manifest.json"):
            skill_dir = m_file.parent.resolve()

            if skill_dir in protected_roots:
                logger.warning(
                    f"Skipping deletion at {m_file}: Manifest is located directly in root directory {skill_dir}."
                )
                continue

            try:
                with open(m_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                pkg = (data.get("package") or data.get("skill_id") or "").lower()
                action_ids = [
                    a.get("skill_id", "").lower()
                    for a in data.get("actions", [])
                    if isinstance(a, dict)
                ]

                if (
                    pkg in (clean_id.lower(), skill_id.lower())
                    or skill_dir.name.lower() in (clean_id.lower(), skill_id.lower())
                    or clean_id.lower() in action_ids
                    or skill_id.lower() in action_ids
                ):
                    dirs_to_delete.add(skill_dir)
            except Exception as e:
                logger.error(f"Error inspecting manifest at {m_file}: {e}")

    deleted_paths: List[Path] = []
    for skill_dir in dirs_to_delete:
        if skill_dir in protected_roots:
            continue

        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            deleted_paths.append(skill_dir)

    if not deleted_paths:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate any skill folder matching '{skill_id}'."
        )
        return 1

    _cleanup_agent_mappings_for_skill(clean_id)
    _cleanup_agent_mappings_for_skill(skill_id)

    for p in deleted_paths:
        console.print(f"[bold yellow]🗑️ Purged directory:[/bold yellow] {p}")

    console.print(
        f"[bold green]✅ Successfully deleted skill '[bold cyan]{skill_id}[/bold cyan]'.[/bold green]"
    )
    return run_sync()