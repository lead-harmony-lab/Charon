#!/usr/bin/env python3
"""
scripts/inspect_skill_manifests.py
System Version: v0.6.3 (Read-Only)

Pass 1 Manifest Auditor:
Scans all 38 skill directories on disk, parses manifest.json files, inspects
metadata structure (actions, parameters, schemas), and reports missing/incomplete fields
without modifying state.db.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.ManifestInspector")


def inspect_manifests():
    if not SKILLS_DIR.exists():
        logger.error(f"Directory not found: {SKILLS_DIR}")
        return

    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]

    print("\n" + "=" * 90)
    print(f" 🔍 PASS 1: MANIFEST INSPECTION REPORT ({len(skill_folders)} Directories Found)")
    print("=" * 90 + "\n")

    total_actions_found = 0
    anomalies: List[Dict[str, Any]] = []
    parsed_skills: List[Dict[str, Any]] = []

    for folder in sorted(skill_folders):
        folder_name = folder.name
        manifest_path = folder / "manifest.json"
        plugin_path = folder / "plugin.py"

        folder_info = {
            "folder": folder_name,
            "has_manifest": manifest_path.exists(),
            "has_plugin": plugin_path.exists(),
            "actions": [],
            "warnings": [],
        }

        if not manifest_path.exists():
            folder_info["warnings"].append("Missing manifest.json")
            anomalies.append(folder_info)
            continue

        if not plugin_path.exists():
            folder_info["warnings"].append("Missing plugin.py")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Determine manifest schema type (top-level vs actions array)
            raw_actions = []
            if "actions" in data and isinstance(data["actions"], list):
                raw_actions = data["actions"]
            elif "action_name" in data or "name" in data:
                raw_actions = [data]
            else:
                folder_info["warnings"].append(
                    "Unrecognized schema format (no 'actions' list or 'action_name' root key)")

            for idx, act in enumerate(raw_actions):
                action_name = act.get("action_name") or act.get("name") or "UNNAMED_ACTION"
                skill_id = act.get("skill_id") or f"sk_{action_name}"
                description = act.get("description", "").strip()
                params = act.get("parameters", {})
                version = act.get("version", data.get("version", "N/A"))
                category = act.get("category", data.get("category", "Uncategorized"))

                action_meta = {
                    "skill_id": skill_id,
                    "action_name": action_name,
                    "version": version,
                    "category": category,
                    "desc_len": len(description),
                    "param_count": len(params.get("properties", params)) if isinstance(params, dict) else 0,
                    "has_desc": bool(description),
                }

                # Missing field checks
                missing_fields = []
                if not action_name or action_name == "UNNAMED_ACTION":
                    missing_fields.append("action_name")
                if not description:
                    missing_fields.append("description")
                if not params:
                    missing_fields.append("parameters")

                if missing_fields:
                    folder_info["warnings"].append(f"Action '{action_name}' missing: {', '.join(missing_fields)}")

                folder_info["actions"].append(action_meta)
                total_actions_found += 1

        except json.JSONDecodeError as e:
            folder_info["warnings"].append(f"Invalid JSON format: {e}")
        except Exception as e:
            folder_info["warnings"].append(f"Unexpected error: {e}")

        if folder_info["warnings"]:
            anomalies.append(folder_info)

        parsed_skills.append(folder_info)

    # Output Detailed Breakdown Table
    print(f"{'FOLDER NAME':<33} | {'ACTIONS':<8} | {'PLUGIN?':<8} | {'STATUS / WARNINGS'}")
    print("-" * 90)

    for item in parsed_skills:
        f_name = item["folder"]
        act_cnt = len(item["actions"])
        has_p = "Yes" if item["has_plugin"] else "NO"
        warn_str = " OK" if not item["warnings"] else f"⚠️ {'; '.join(item['warnings'])}"

        print(f"{f_name:<33} | {act_cnt:<8} | {has_p:<8} | {warn_str}")

    print("-" * 90)
    print("\n" + "=" * 90)
    print(" 📊 METADATA SUMMARY & AUDIT TOTALS")
    print("=" * 90)
    print(f" Total Skill Directories Scanned : {len(skill_folders)}")
    print(f" Total Discrete Actions Discovered: {total_actions_found}")
    print(f" Folders With Schema Warnings    : {len(anomalies)}")
    print("=" * 90 + "\n")

    if anomalies:
        print("🚨 DETAILED ANOMALY / INCOMPLETE FIELD REPORT:")
        print("-" * 90)
        for a in anomalies:
            print(f" Folder: {a['folder']}")
            for w in a["warnings"]:
                print(f"  └── ⚠️  {w}")
        print("-" * 90 + "\n")


if __name__ == "__main__":
    inspect_manifests()