"""
charon/cli/librarian/diagnostics_core.py
System Version: v0.2.2 | File Revision: 2.4.0

Module: System diagnostics, manifest normalization, binary system dependencies, and AST healing.
All database operations are strictly delegated to charon.cli.librarian.db.
"""

import ast
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from charon.cli.librarian.db import (
    cleanup_orphaned_agent_mappings_db,
    get_deficient_skills_db,
    get_quarantined_skills_db,
    purge_skill_records,
    repair_quarantined_skill_db,
)
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)
from charon.core.skills import SkillLibrarian

PACKAGE_MAP = {
    "tesseract": "tesseract-ocr",
    "kicad-cli": "kicad",
    "node": "nodejs",
    "python": "python3",
    "ffmpeg": "ffmpeg",
    "pdftoppm": "poppler-utils",
}


def cleanup_orphaned_agent_mappings() -> int:
    """Purges orphaned records from agent_skill_map where skill_id no longer exists."""
    return cleanup_orphaned_agent_mappings_db()


def normalize_manifest_action_contracts(
    librarian: SkillLibrarian, dry_run: bool = False
) -> int:
    """Converts supported_actions keys into 3-node canonical names on disk."""
    if hasattr(librarian, "_discover_manifests"):
        manifests = librarian._discover_manifests()
    else:
        search_paths = getattr(
            librarian,
            "search_paths",
            [PKG_STAGED_SKILLS_DIR, PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR],
        )
        manifests = [
            p
            for path in search_paths
            if path.exists()
            for p in path.rglob("manifest.json")
        ]

    updated_count = 0

    for manifest_path in manifests:
        try:
            raw_text = manifest_path.read_text(encoding="utf-8")
            data: Dict[str, Any] = json.loads(raw_text)

            skill_id = data.get("skill_id", manifest_path.parent.name)
            category = data.get("category", "general")
            supported_actions = data.get("supported_actions", {})

            if not supported_actions:
                continue

            modified = False
            normalized_actions: Dict[str, Any] = {}

            for raw_action, action_def in supported_actions.items():
                if hasattr(librarian, "_derive_canonical_action_name"):
                    canonical_name = librarian._derive_canonical_action_name(
                        category=category,
                        skill_id=skill_id,
                        raw_action=raw_action,
                    )
                else:
                    clean_cat = (
                        category.lower().strip().replace("-", "_").replace(" ", "_")
                    )
                    clean_verb = (
                        raw_action.lower().strip().replace("-", "_").replace(" ", "_")
                    )

                    if clean_verb.count("_") >= 2 and clean_verb.startswith(
                        f"{clean_cat}_"
                    ):
                        canonical_name = clean_verb
                    else:
                        clean_skill = (
                            skill_id.lower()
                            .strip()
                            .replace("-", "_")
                            .replace(" ", "_")
                            .replace("skill_", "")
                        )
                        context_node = (
                            clean_skill[len(f"{clean_cat}_") :].split("_")[0]
                            if clean_skill.startswith(f"{clean_cat}_")
                            else clean_skill.split("_")[0]
                        )
                        if not context_node or context_node == clean_verb:
                            base_verb = clean_verb.split("_")[0]
                            context_node = (
                                f"{base_verb}r"
                                if base_verb.endswith("e")
                                else f"{base_verb}er"
                            )
                        canonical_name = f"{clean_cat}_{context_node}_{clean_verb}"

                if canonical_name != raw_action:
                    modified = True

                if isinstance(action_def, dict):
                    action_payload = dict(action_def)
                    if (
                        "handler" not in action_payload
                        and "handler_name" not in action_payload
                    ):
                        action_payload["handler"] = (
                            f"handle_{raw_action.replace(' ', '_').replace('-', '_')}"
                        )
                else:
                    action_payload = {
                        "description": f"Executes '{canonical_name}'",
                        "handler": str(action_def),
                        "parameters": {},
                    }

                normalized_actions[canonical_name] = action_payload

            if modified:
                data["supported_actions"] = normalized_actions
                updated_count += 1
                if not dry_run:
                    manifest_path.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
        except Exception:
            pass

    return updated_count


def get_deficient_skills() -> List[Tuple]:
    """Retrieves skills missing parameters or artifacts."""
    return get_deficient_skills_db()


def process_ast_healing(deficient_skills: List[Tuple]) -> Tuple[int, int, int]:
    """Cracks open plugin.py via AST and heals manifest.json.

    Auto-injects the alias contract into plugin.py if it is missing, ensuring
    the DB's 3-node contract maps to the dev's code. Returns: (healed_count,
    verified_empty_count, not_found_count)
    """
    healed_count = 0
    verified_empty = 0
    not_found = 0

    for skill_id, action_name, db_handler_name, entry_file_path in deficient_skills:
        if not entry_file_path:
            continue

        base_path = Path(entry_file_path)

        if base_path.is_file():
            entry_file = base_path
            manifest_file = base_path.parent / "manifest.json"
        else:
            entry_file = base_path / "plugin.py"
            manifest_file = base_path / "manifest.json"

        if not entry_file.exists():
            if base_path.is_dir():
                py_files = list(base_path.glob("*.py"))
                if py_files:
                    entry_file = py_files[0]
                else:
                    not_found += 1
                    continue
            else:
                not_found += 1
                continue

        if not manifest_file.exists():
            not_found += 1
            continue

        try:
            tree = ast.parse(entry_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        target_func_name = db_handler_name
        alias_found = False

        # 1. AST PASS ONE: Resolve Aliases
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == db_handler_name
                    ):
                        alias_found = True
                        if isinstance(node.value, ast.Name):
                            target_func_name = node.value.id
                        elif isinstance(node.value, ast.Attribute):
                            target_func_name = node.value.attr
                        break

        # 2. AUTO-INJECT MISSING ALIAS
        if not alias_found:
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)

                dev_handler = None
                supported_actions = manifest_data.get("supported_actions", {})
                action_def = supported_actions.get(action_name)

                if isinstance(action_def, dict):
                    dev_handler = action_def.get(
                        "handler", action_def.get("handler_name")
                    )
                elif isinstance(action_def, str):
                    dev_handler = action_def

                if dev_handler and dev_handler != db_handler_name:
                    # Physically append the alias to the python file
                    with open(entry_file, "a", encoding="utf-8") as f:
                        f.write(
                            f"\n\n# [Charon Harness] Alias Contract\n{db_handler_name} = {dev_handler}\n"
                        )

                    # Reload the AST with the new alias injected
                    tree = ast.parse(entry_file.read_text(encoding="utf-8"))
                    target_func_name = dev_handler
            except Exception:
                pass

        target_func_name = target_func_name.split(".")[-1]

        # 3. AST PASS TWO: Locate Function Definition
        handler_node = None
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == target_func_name
            ):
                handler_node = node
                break

        if not handler_node:
            not_found += 1
            continue

        derived_params = {}
        derived_produced = []

        # 4. Extract Positional Arguments & Defaults
        args = handler_node.args.args
        defaults = handler_node.args.defaults
        default_offset = len(args) - len(defaults)

        for i, arg in enumerate(args):
            arg_name = arg.arg
            if arg_name in ("self", "cls", "context"):
                continue

            required = i < default_offset
            arg_type = "string"

            if arg.annotation:
                if hasattr(ast, "unparse"):
                    arg_type = ast.unparse(arg.annotation)
                elif isinstance(arg.annotation, ast.Name):
                    arg_type = arg.annotation.id.lower()

            derived_params[arg_name] = {
                "type": arg_type,
                "description": f"Auto-extracted parameter: {arg_name}",
                "required": required,
            }

        # 5. Extract Keyword-Only Arguments
        kwonlyargs = handler_node.args.kwonlyargs
        kw_defaults = handler_node.args.kw_defaults
        for i, arg in enumerate(kwonlyargs):
            arg_name = arg.arg
            required = kw_defaults[i] is None
            arg_type = "string"
            if arg.annotation:
                if hasattr(ast, "unparse"):
                    arg_type = ast.unparse(arg.annotation)
                elif isinstance(arg.annotation, ast.Name):
                    arg_type = arg.annotation.id.lower()

            derived_params[arg_name] = {
                "type": arg_type,
                "description": f"Auto-extracted kwarg: {arg_name}",
                "required": required,
            }

        # 6. Extract Return Annotations
        if handler_node.returns:
            if hasattr(ast, "unparse"):
                derived_produced.append(ast.unparse(handler_node.returns))
            elif isinstance(handler_node.returns, ast.Name):
                derived_produced.append(handler_node.returns.id)
            elif isinstance(
                handler_node.returns, ast.Subscript
            ) and hasattr(handler_node.returns.slice, "id"):
                derived_produced.append(handler_node.returns.slice.id)

        # 7. Determine if legitimately empty
        if not derived_params and not derived_produced:
            verified_empty += 1
            continue

        # 8. Patch the manifest.json
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            modified = False

            if (
                "supported_actions" in manifest_data
                and action_name in manifest_data["supported_actions"]
            ):
                action_def = manifest_data["supported_actions"][action_name]
                if not action_def.get("parameters") and derived_params:
                    action_def["parameters"] = derived_params
                    modified = True
            else:
                if (
                    not manifest_data.get("action_parameters", {}).get(
                        action_name
                    )
                    and derived_params
                ):
                    manifest_data.setdefault("action_parameters", {})[
                        action_name
                    ] = derived_params
                    modified = True

            if not manifest_data.get("produced_artifacts") and derived_produced:
                manifest_data["produced_artifacts"] = derived_produced
                modified = True

            if modified:
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest_data, f, indent=4)
                healed_count += 1
            else:
                verified_empty += 1

        except Exception:
            pass

    return healed_count, verified_empty, not_found


def get_quarantined_skills() -> List[Tuple]:
    """Fetches list of currently quarantined skills."""
    return get_quarantined_skills_db()


def delete_quarantined_skill(skill_id: str) -> None:
    """Deletes a skill and its agent mappings from the database."""
    purge_skill_records(skill_id)


def repair_quarantined_skill(skill_id: str, path_str: str) -> bool:
    """Attempts to reactivate a quarantined skill if files exist."""
    entry_path = Path(path_str) if path_str else None
    if entry_path and entry_path.exists():
        return repair_quarantined_skill_db(skill_id)
    return False


def build_apt_command(broken_skills: List[Dict]) -> Tuple[set, str, str]:
    """Generates the apt command string and maps missing binaries."""
    missing_binaries = set()
    for s in broken_skills:
        missing_binaries.update(s.get("missing_requirements", []))

    apt_packages = [PACKAGE_MAP.get(b, b) for b in missing_binaries]
    pkg_str = " ".join(apt_packages)
    cmd = f"sudo apt-get update && sudo apt-get install -y {pkg_str}"

    return missing_binaries, pkg_str, cmd


def execute_apt_command(cmd: str) -> None:
    """Fires the apt subprocess."""
    subprocess.run(cmd, shell=True)