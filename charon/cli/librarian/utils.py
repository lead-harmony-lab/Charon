"""
charon/cli/librarian/utils.py

Module: Pure functions for string normalization, naming conventions,
and template hydration.
"""
import re
from pathlib import Path
from typing import Optional

SKILLS_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "skills" / "templates"

def slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", (text or "").lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")

def derive_action_name(raw_name: str) -> str:
    """Derives a standard action_name from a string or skill_id."""
    clean = slugify(raw_name)
    parts = clean.split("_")
    if parts and parts[0] == "skill":
        parts = parts[1:]

    if len(parts) > 1:
        suffix = parts[-1]
        verb_map = {
            "executor": "execute", "generator": "generate",
            "evaluator": "evaluate", "analyzer": "analyze",
            "builder": "build", "synthesizer": "synthesize",
        }
        return verb_map.get(suffix, suffix)

    return parts[0] if parts else "execute"

def get_template_content(filename: str, replacements: Optional[dict] = None) -> str:
    """Reads a template file and replaces double-curly placeholders."""
    template_path = SKILLS_TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Required template file missing at: {template_path}")

    content = template_path.read_text(encoding="utf-8")
    if replacements:
        for key, value in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
    return content