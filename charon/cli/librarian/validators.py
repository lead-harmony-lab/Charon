"""
charon/cli/librarian/validators.py

Module: Defensive validation, AST parsing, and collision detection for untrusted skills.
"""
import ast
from pathlib import Path
from typing import Optional, Tuple

from charon.config.paths import (
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_QUARANTINE_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)

def is_skill_id_taken(skill_id: str, ignore_path: Optional[Path] = None) -> bool:
    """Checks if a skill identifier already exists in any storage."""
    paths = [
        PKG_QUARANTINE_SKILLS_DIR / skill_id,
        PKG_STAGED_SKILLS_DIR / skill_id,
        PKG_DYNAMIC_SKILLS_DIR / skill_id
    ]
    if ignore_path:
        paths = [p for p in paths if p.resolve() != ignore_path.resolve()]

    return any(p.exists() for p in paths)

def verify_plugin_entrypoint(plugin_path: Path) -> Tuple[bool, str]:
    """Uses AST parsing to verify that plugin.py is syntactically valid and exposes a handler."""
    if not plugin_path.exists():
        return False, f"Plugin file missing at: {plugin_path}"

    try:
        tree = ast.parse(plugin_path.read_text(encoding="utf-8"), filename=str(plugin_path))
        declared_functions = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        has_valid_entrypoint = "execute_action" in declared_functions or any(
            f == "run" or f.startswith("handle_") for f in declared_functions
        )

        if not has_valid_entrypoint:
            return False, "Plugin must define 'execute_action', 'run', or a 'handle_*' function handler."

        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in plugin file '{plugin_path.name}': {e}"