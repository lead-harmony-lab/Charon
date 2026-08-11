"""
charon/cli/librarian/ingestion.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Dynamic skill creation, file ingestion, and interactive $EDITOR editing launcher.
Templates are dynamically loaded from charon/skills/templates/ rather than hardcoded.
Refactored with AST pre-validation, schema compliance checks, transaction safety,
and interactive skill identifier resolution with collision prevention.
"""

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Optional, Tuple

from rich.console import Console
from rich.prompt import Confirm, Prompt

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest
from charon.cli.librarian.service import register_and_bind_skill
from charon.config.paths import PKG_DYNAMIC_SKILLS_DIR, PKG_STAGED_SKILLS_DIR

console = Console()

SKILLS_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "skills" / "templates"
)


def _slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def is_skill_id_taken(skill_id: str) -> bool:
    """Checks if a skill identifier already exists in staged or dynamic registries."""
    staged_path = PKG_STAGED_SKILLS_DIR / skill_id
    dynamic_path = PKG_DYNAMIC_SKILLS_DIR / skill_id
    return staged_path.exists() or dynamic_path.exists()


def resolve_ingestion_skill_id(
    source_path: Path, explicit_id: Optional[str] = None
) -> Optional[str]:
    """Interactively resolves and validates a non-colliding skill identifier with the user."""
    manifest_id = None

    # Pre-read manifest skill_id if source is a directory with a manifest
    if source_path.is_dir():
        manifest_file = source_path / "manifest.json"
        if manifest_file.exists():
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest_id = data.get("skill_id")
            except Exception:
                pass

    raw_proposed = explicit_id or manifest_id or source_path.stem
    proposed_id = _slugify(raw_proposed)

    console.print("\n[bold cyan]📦 Skill Ingestion Setup[/bold cyan]")
    console.print(f"Target Source: [dim]{source_path}[/dim]")
    console.print(f"Proposed Skill ID: [bold yellow]{proposed_id}[/bold yellow]")

    # Check for collision on proposed name
    if is_skill_id_taken(proposed_id):
        console.print(
            f"[bold red]⚠️ Collision Alert:[/bold red] Skill ID '[cyan]{proposed_id}[/cyan]' already exists in staged or dynamic registries."
        )
        use_proposed = False
    else:
        use_proposed = Confirm.ask(
            f"Ingest skill using identifier '[bold green]{proposed_id}[/bold green]'?",
            default=True,
        )

    if use_proposed:
        return proposed_id

    # Interactive prompt loop for custom identifier
    while True:
        custom_input = Prompt.ask(
            "\n[bold cyan]Enter custom skill identifier[/bold cyan] (or 'cancel' to abort)"
        ).strip()

        if custom_input.lower() == "cancel" or not custom_input:
            console.print("[yellow]Ingestion cancelled by user.[/yellow]")
            return None

        clean_id = _slugify(custom_input)

        if not clean_id:
            console.print(
                "[bold red]Error:[/bold red] Invalid identifier. Must contain alphanumeric characters."
            )
            continue

        if is_skill_id_taken(clean_id):
            console.print(
                f"[bold red]Error:[/bold red] Skill ID '[cyan]{clean_id}[/cyan]' is already taken. Please choose another."
            )
            continue

        console.print(f"[bold green]✓ Approved identifier:[/bold green] {clean_id}")
        return clean_id


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


def verify_plugin_entrypoint(plugin_path: Path) -> Tuple[bool, str]:
    """Uses AST parsing to verify that plugin.py is syntactically valid and exposes a handler."""
    if not plugin_path.exists():
        return False, f"Plugin file missing at: {plugin_path}"

    try:
        tree = ast.parse(plugin_path.read_text(encoding="utf-8"), filename=str(plugin_path))
        declared_functions = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }

        # Plugin must define execute_action OR at least one handle_* function
        if "execute_action" not in declared_functions and not any(
            f.startswith("handle_") for f in declared_functions
        ):
            return (
                False,
                "Plugin must define 'execute_action' router or at least one 'handle_<action>' function.",
            )

        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in plugin file '{plugin_path.name}': {e}"


def run_create(skill_id: str, category: str = "General", target_agent: Optional[str] = None) -> int:
    """Scaffolds a new skill template package driven by charon/skills/templates/."""
    clean_skill_id = _slugify(skill_id)

    if is_skill_id_taken(clean_skill_id):
        console.print(
            f"[bold red]Error:[/bold red] Skill ID '[cyan]{clean_skill_id}[/cyan]' already exists in staged or dynamic registries."
        )
        return 1

    target_dir = PKG_STAGED_SKILLS_DIR / clean_skill_id
    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": clean_skill_id, "CATEGORY": category}

    try:
        manifest_content = get_template_content("manifest.json", replacements)
        plugin_content = get_template_content("plugin.py", replacements)

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        manifest_path.write_text(manifest_content, encoding="utf-8")
        plugin_path.write_text(plugin_content, encoding="utf-8")

        # 1. AST Static Verification
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            console.print(f"[bold red]AST Validation Error:[/bold red] {ast_err}")
            shutil.rmtree(target_dir)
            return 1

        manifest_data = json.loads(manifest_content)

        # 2. Atomic Registration & Binding
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        console.print(
            f"[bold green]✅ Scaffolded and bound new skill '[cyan]{clean_skill_id}[/cyan]' at:[/bold green] {target_dir}"
        )
        return run_sync()

    except Exception as e:
        console.print(f"[bold red]Error creating skill scaffold:[/bold red] {e}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        return 1


def run_ingest(source_path: Path, skill_id: Optional[str] = None, target_agent: Optional[str] = None) -> int:
    """Ingests external standalone Python files or folders into staged skills using templates for fallbacks."""
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        console.print(f"[bold red]Error:[/bold red] Source path '{source_path}' does not exist.")
        return 1

    sid = resolve_ingestion_skill_id(source_path, explicit_id=skill_id)
    if not sid:
        return 1

    target_dir = PKG_STAGED_SKILLS_DIR / sid

    if target_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Staged directory '[cyan]{sid}[/cyan]' already exists at {target_dir}"
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": sid, "CATEGORY": "Ingested"}

    try:
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
                    plugin_content = get_template_content("plugin.py", replacements)
                    (target_dir / "plugin.py").write_text(plugin_content, encoding="utf-8")

            if not (target_dir / "manifest.json").exists():
                console.print(
                    "[yellow]No manifest.json found in directory. Generating schema scaffold from template...[/yellow]"
                )
                manifest_content = get_template_content("manifest.json", replacements)
                (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        # Force manifest skill_id parity with approved folder identifier
        if manifest_path.exists():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                mdata["skill_id"] = sid
                manifest_path.write_text(json.dumps(mdata, indent=2), encoding="utf-8")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not update manifest skill_id field: {e}[/yellow]")

        # 1. AST Entrypoint Verification
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            console.print(f"[bold red]AST Validation Error:[/bold red] {ast_err}")
            shutil.rmtree(target_dir)
            return 1

        # 2. Schema Integrity Check
        is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
        if not is_valid:
            console.print(
                "[bold red]❌ Manifest failed schema validation:[/bold red]\n"
                + "\n".join(errors)
            )
            shutil.rmtree(target_dir)
            return 1

        # 3. Register and Bind
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        console.print(
            f"[bold green]✅ Ingested '[cyan]{sid}[/cyan]' into staged skills at {target_dir}.[/bold green]"
        )
        return run_sync()

    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        return 1


def run_edit(skill_id: str) -> int:
    """Opens a skill manifest in $EDITOR, then validates and syncs automatically on exit."""
    manifest_path = find_skill_manifest(skill_id)
    if not manifest_path:
        console.print(f"[bold red]Error:[/bold red] Could not locate skill '{skill_id}'.")
        return 1

    editor = os.environ.get("EDITOR", "nano")
    console.print(f"[bold cyan]Opening {manifest_path} with {editor}...[/bold cyan]")
    subprocess.call([editor, str(manifest_path)])

    is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
    if not is_valid:
        console.print(
            "[bold red]❌ Manifest contains schema errors after edit:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    console.print("[bold green]✅ Manifest validation passed.[/bold green]")
    return run_sync()