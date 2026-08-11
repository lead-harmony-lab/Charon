#!/usr/bin/env python3
"""
scripts/preview_manifest_indexing.py
System Version: v0.6.5 (Read-Only Preview)

Parses all 38 skill manifests using supported_actions, applies DB field mappings,
and prints the resulting action table to verify everything before writing to state.db.
"""

import json
from pathlib import Path

SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def preview_indexing():
    if not SKILLS_DIR.exists():
        print(f"Error: Directory not found at {SKILLS_DIR}")
        return

    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]
    all_actions = []

    for folder in sorted(skill_folders):
        manifest_path = folder / "manifest.json"
        plugin_path = folder / "plugin.py"

        if not manifest_path.exists() or not plugin_path.exists():
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            version = data.get("version", "1.0.0")
            category = data.get("category", "General")
            sys_reqs = json.dumps(data.get("system_requirements", []))
            supported_actions = data.get("supported_actions", {})

            for action_name, action_meta in supported_actions.items():
                skill_id = f"sk_{action_name}"
                description = action_meta.get("description", "").strip()
                parameters = json.dumps(action_meta.get("parameters", {}))
                handler_name = action_name  # Standard handler naming convention

                all_actions.append({
                    "skill_id": skill_id,
                    "action_name": action_name,
                    "folder": folder.name,
                    "version": version,
                    "category": category,
                    "description": description[:50] + "..." if len(description) > 50 else description,
                    "entry_file_path": str(plugin_path),
                    "handler_name": handler_name,
                })

        except Exception as e:
            print(f"⚠️ Error parsing {manifest_path}: {e}")

    print("\n" + "=" * 95)
    print(f" 📑 DISCOVERED ACTIONS PREVIEW ({len(all_actions)} Total Actions Across 38 Folders)")
    print("=" * 95)
    print(f"{'SKILL ID':<28} | {'ACTION NAME':<25} | {'CATEGORY':<20} | {'FOLDER'}")
    print("-" * 95)

    for act in all_actions:
        print(f"{act['skill_id']:<28} | {act['action_name']:<25} | {act['category']:<20} | {act['folder']}")

    print("-" * 95)
    print(f"\nTotal actions to be indexed into skill_registry: {len(all_actions)}\n")


if __name__ == "__main__":
    preview_indexing()