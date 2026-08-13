"""Data normalization and hydration helpers for skill inspection."""

import json
from pathlib import Path
from typing import Any, Dict, List
from rich.console import Console

console = Console()


def parse_list(val: Any) -> List[str]:
    """Safely normalizes raw input (strings, JSON strings, lists) into a list of strings."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def parse_supported_actions(actions_raw: Any) -> Dict[str, Any]:
    """Ensures supported_actions is always a dictionary, deserializing JSON strings if necessary."""
    if isinstance(actions_raw, str):
        try:
            actions_raw = json.loads(actions_raw)
        except Exception:
            return {}
    return actions_raw if isinstance(actions_raw, dict) else {}


def extract_handler_name(action_info: Any) -> str:
    """Extracts handler function name whether action value is a dict or a direct string."""
    if isinstance(action_info, dict):
        return str(action_info.get("handler") or action_info.get("handler_name") or "N/A")
    elif isinstance(action_info, str):
        return action_info
    return "N/A"


def extract_action_desc(action_info: Any) -> str:
    """Extracts action description safely if present."""
    if isinstance(action_info, dict):
        return str(action_info.get("description") or "")
    return ""


def hydrate_skill_from_manifest(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Hydrates skill metadata directly from manifest.json on disk."""
    manifest_path_str = skill.get("manifest_path")
    if not manifest_path_str:
        return skill

    manifest_path = Path(manifest_path_str)
    if not manifest_path.exists():
        return skill

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("skill_id"):
            skill["skill_id"] = data["skill_id"]
        if data.get("category"):
            skill["category"] = data["category"]
        if data.get("description"):
            skill["description"] = data["description"]
        if data.get("version"):
            skill["version"] = data["version"]

        entry_point = data.get("entry_point") or data.get("entry_file") or "plugin.py"
        resolved_entry = (manifest_path.parent / entry_point).resolve()
        if resolved_entry.exists():
            skill["entry_file_path"] = str(resolved_entry)
        elif not skill.get("entry_file_path"):
            skill["entry_file_path"] = str(manifest_path.parent / entry_point)

        if "supported_actions" in data:
            skill["supported_actions"] = parse_supported_actions(data["supported_actions"])
        if "system_requirements" in data and not skill.get("system_requirements"):
            skill["system_requirements"] = parse_list(data["system_requirements"])
        if "allowed_agents" in data and not skill.get("authorized_agents"):
            skill["authorized_agents"] = parse_list(data["allowed_agents"])

    except Exception as e:
        console.print(f"[dim red]Warning: Could not read manifest at {manifest_path}: {e}[/dim red]")

    return skill