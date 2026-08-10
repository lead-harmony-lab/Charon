"""
charon/cli/librarian/ingestion.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Dynamic skill creation, file ingestion, and interactive $EDITOR editing launcher.
Templates are dynamically loaded from charon/skills/templates/ rather than hardcoded.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Optional

from rich.console import Console

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest
from charon.cli.librarian.service import register_and_bind_skill
from charon.config.paths import PKG_STAGED_SKILLS_DIR

console = Console()

SKILLS_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "skills" / "templates"
)


def get_template_content(
    filename: str, replacements: Optional[dict] = None
) -> str:
    """Reads a template file from charon/skills/templates and replaces double-curly placeholders."""
    template_path = SKILLS_TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(
            f"Required template file missing at: {template_path}"
        )

    content = template_path.read_text(encoding="utf-8")
    if replacements:
        for key, value in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def run_create(skill_id: str, category: str = "General", target_agent: Optional[str] = None) -> int:
    """Scaffolds a new skill template package driven by charon/skills/templates/."""
    target_dir = PKG_STAGED_SKILLS_DIR / skill_id
    if target_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Target directory already exists: {target_dir}"
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": skill_id, "CATEGORY": category}

    try:
        manifest_content = get_template_content("manifest.json", replacements)
        plugin_content = get_template_content("plugin.py", replacements)

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        manifest_path.write_text(manifest_content, encoding="utf-8")
        plugin_path.write_text(plugin_content, encoding="utf-8")

        manifest_data = json.loads(manifest_content)

        # Atomic 4-step registration & binding
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        console.print(
            f"[bold green]✅ Scaffolded and bound new skill '[cyan]{skill_id}[/cyan]' at:[/bold green] {target_dir}"
        )
        return run_sync()
    except Exception as e:
        console.print(
            f"[bold red]Error creating skill scaffold:[/bold red] {e}"
        )
        return 1


def run_ingest(source_path: Path, skill_id: Optional[str] = None, target_agent: Optional[str] = None) -> int:
    """Ingests external standalone Python files or folders into staged skills using templates for fallback metadata."""
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        console.print(
            f"[bold red]Error:[/bold red] Source path '{source_path}' does not exist."
        )
        return 1

    sid = (
        skill_id
        or source_path.stem.lower().replace("-", "_").replace(" ", "_")
    )
    target_dir = PKG_STAGED_SKILLS_DIR / sid

    if target_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Staged directory '[cyan]{sid}[/cyan]' already exists at {target_dir}"
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": sid, "CATEGORY": "Ingested"}

    if source_path.is_file():
        shutil.copy(source_path, target_dir / "plugin.py")
        manifest_content = get_template_content("manifest.json", replacements)
        (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

    elif source_path.is_dir():
        shutil.copytree(source_path, target_dir, dirs_exist_ok=True)

        if not (target_dir / "plugin.py").exists():
            py_files = list(target_dir.glob("*.py"))
            if len(py_files) == 1:
                py_files[0].rename(target_dir / "plugin.py")
            elif not py_files:
                plugin_content = get_template_content(
                    "plugin.py", replacements
                )
                (target_dir / "plugin.py").write_text(plugin_content, encoding="utf-8")

        if not (target_dir / "manifest.json").exists():
            console.print(
                "[yellow]No manifest.json found in directory. Generating schema scaffold from template...[/yellow]"
            )
            manifest_content = get_template_content(
                "manifest.json", replacements
            )
            (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

    manifest_path = target_dir / "manifest.json"
    plugin_path = target_dir / "plugin.py"

    if manifest_path.exists() and plugin_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            register_and_bind_skill(
                skill_manifest=manifest_data,
                entry_file_path=plugin_path,
                target_agent_id=target_agent,
            )
        except Exception as e:
            console.print(f"[bold yellow]Warning:[/bold yellow] Pre-binding helper skipped ({e}). Executing indexer sync...")

    console.print(
        f"[bold green]✅ Ingested '[cyan]{sid}[/cyan]' into staged skills at {target_dir}.[/bold green]"
    )
    return run_sync()


def run_edit(skill_id: str) -> int:
    """Opens a skill manifest in $EDITOR, then validates and syncs automatically on exit."""
    manifest_path = find_skill_manifest(skill_id)
    if not manifest_path:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate skill '{skill_id}'."
        )
        return 1

    editor = os.environ.get("EDITOR", "nano")
    console.print(
        f"[bold cyan]Opening {manifest_path} with {editor}...[/bold cyan]"
    )
    subprocess.call([editor, str(manifest_path)])

    is_valid, errors, _ = validate_manifest_file(
        manifest_path, auto_fix=True
    )
    if not is_valid:
        console.print(
            f"[bold red]❌ Manifest contains schema errors after edit:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    console.print("[bold green]✅ Validation passed.[/bold green]")
    return run_sync()