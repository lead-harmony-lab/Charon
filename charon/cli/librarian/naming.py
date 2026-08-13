"""
charon/cli/librarian/naming.py
System Version: v0.6.5 | File Revision: 1.0.0

Module: Naming heuristics and fuzzy 3-node action key generator for preventing
collisions between skill_id and action_name during lifecycle promotions.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, Tuple


def sanitize_node(text: str) -> str:
    """Cleans a string into a single lowercase alphanumeric node word."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", text).lower()
    return cleaned or "core"


def derive_fuzzy_3node_action_name(skill_id: str, manifest_data: Dict[str, Any]) -> str:
    """
    Generates a unique 3-node action name (node1_node2_node3) using fuzzy heuristics
    derived from manifest category, handler function name, and supported_actions.
    Ensures the generated action_name does NOT equal skill_id.
    """
    category = sanitize_node(manifest_data.get("category", "execution"))

    # Extract raw handler or description text for verb/target clues
    supported = manifest_data.get("supported_actions", {})
    handler_str = ""
    if isinstance(supported, dict) and supported:
        first_val = list(supported.values())[0]
        if isinstance(first_val, dict):
            handler_str = str(first_val.get("handler") or first_val.get("handler_name") or "")
        elif isinstance(first_val, str):
            handler_str = first_val

    # Strip common handler prefixes/suffixes like "handle_" or "_fn"
    clean_handler = re.sub(r"^(handle_|run_|do_)", "", handler_str.lower())
    clean_handler = re.sub(r"(_handler|_fn|_action)$", "", clean_handler)

    # Tokenize skill_id to find constituent words
    skill_tokens = [sanitize_node(t) for t in skill_id.split("_") if t.strip()]

    # Node 1: Domain / Category
    node1 = category if category else (skill_tokens[0] if skill_tokens else "system")

    # Node 2: Target / Subject
    if len(skill_tokens) > 1:
        node2 = skill_tokens[1]
    elif clean_handler:
        node2 = sanitize_node(clean_handler.split("_")[0])
    else:
        node2 = "process"

    # Node 3: Action / Verb
    possible_verbs = ["run", "execute", "process", "handle", "dispatch", "invoke", "output"]
    handler_tokens = [sanitize_node(t) for t in clean_handler.split("_") if t.strip()]

    node3 = "run"
    for token in handler_tokens:
        if token not in (node1, node2) and token not in ("synthesizer", "plugin", "skill"):
            node3 = token
            break

    candidate = f"{node1}_{node2}_{node3}"

    # Fallback rotation if candidate still equals skill_id or isn't 3 distinct nodes
    if candidate == skill_id:
        for v in possible_verbs:
            alt_candidate = f"{node1}_{node2}_{v}"
            if alt_candidate != skill_id:
                candidate = alt_candidate
                break

    return candidate


def ensure_distinct_action_name(manifest_path_str: str, skill_id: str) -> Tuple[str, bool]:
    """
    Inspects manifest on disk. If action_name == skill_id, updates manifest with
    a fuzzy 3-node action name and saves it back to disk.

    Returns (resolved_action_name, was_updated).
    """
    manifest_path = Path(manifest_path_str)
    if not manifest_path.exists():
        return skill_id, False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        supported = data.get("supported_actions", {})
        primary_action = None

        if isinstance(supported, dict) and supported:
            primary_action = list(supported.keys())[0]

        current_action = data.get("action_name") or primary_action or skill_id

        # Collision Check: action_name equals skill_id
        if current_action == skill_id:
            new_action_name = derive_fuzzy_3node_action_name(skill_id, data)

            # Re-map supported_actions dictionary keys
            if isinstance(supported, dict) and supported:
                new_supported = {}
                for k, v in supported.items():
                    key_to_use = new_action_name if k == skill_id else k
                    new_supported[key_to_use] = v
                data["supported_actions"] = new_supported
            else:
                data["supported_actions"] = {
                    new_action_name: {"handler": "handle_execute", "description": data.get("description", "")}
                }

            data["action_name"] = new_action_name

            # Persist updated manifest back to disk
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")

            return new_action_name, True

        return current_action, False

    except Exception:
        return skill_id, False