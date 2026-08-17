"""
charon/cli/librarian/validators/core.py
System Version: v0.2.1 | File Revision: 3.0.0

Module: AST parsing, entrypoint verification, dependency checks, and skill ID collision detection.
"""
import ast
import importlib.util
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from charon.config.paths import (
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_QUARANTINE_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)

PYPI_TO_MODULE_MAP = {
    "beautifulsoup4": "bs4",
    "paho-mqtt": "paho",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
}


def is_skill_id_taken(skill_id: str, ignore_path: Optional[Path] = None) -> bool:
    """Checks if a skill identifier already exists in any storage target."""
    paths = [
        PKG_QUARANTINE_SKILLS_DIR / skill_id,
        PKG_STAGED_SKILLS_DIR / skill_id,
        PKG_DYNAMIC_SKILLS_DIR / skill_id,
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
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        has_valid_entrypoint = "execute_action" in declared_functions or any(
            f == "run" or f.startswith("handle_") for f in declared_functions
        )

        if not has_valid_entrypoint:
            return (
                False,
                "Plugin must define 'execute_action', 'run', or a 'handle_*' function handler.",
            )

        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in plugin file '{plugin_path.name}': {e}"


def verify_system_dependencies(requirements: List[str]) -> Tuple[bool, List[str]]:
    """
    Checks if required dependencies exist as an OS binary on $PATH or an importable Python module.
    Returns a boolean indicating overall success and a list of any missing requirements.
    """
    if not requirements:
        return True, []

    missing = []
    for req in requirements:
        cleaned_req = req.strip()
        if not cleaned_req:
            continue

        # 1. Check OS binary
        if shutil.which(cleaned_req):
            continue

        # 2. Check Python module
        lower_req = cleaned_req.lower()
        module_name = PYPI_TO_MODULE_MAP.get(lower_req, lower_req)

        try:
            if importlib.util.find_spec(module_name) is not None:
                continue
        except (ImportError, ValueError, AttributeError):
            pass

        # If both fail, record as missing
        missing.append(cleaned_req)

    return len(missing) == 0, missing