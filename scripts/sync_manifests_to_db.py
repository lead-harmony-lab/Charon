#!/usr/bin/env python3
"""
scripts/sync_manifests_to_db.py
System Version: v0.6.7

Pass 2 Database Repair:
Parses all 38 skill directory manifests, resolves skill_id AND action_name
collisions while keeping handler_name aligned with plugin.py functions,
and safely populates skill_registry in charon_state.db.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.Pass2Repair")


def sync_to_db():
    if not STATE_DB_PATH.exists():
        logger.error(f"Database missing at {STATE_DB_PATH}")
        sys.exit(1)

    if not SKILLS_DIR.exists():
        logger.error(f"Skills directory missing at {SKILLS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    seen_action_names = set()
    rows_to_insert = []
    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]

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

            for raw_action_name, action_meta in supported_actions.items():
                handler_name = raw_action_name  # Preserves target python function in plugin.py

                # Resolve action_name and skill_id collisions across distinct plugin folders
                if raw_action_name in seen_action_names:
                    action_name = f"{folder.name}_{raw_action_name}"
                    skill_id = f"sk_{action_name}"
                    logger.warning(
                        f"Collision on action_name '{raw_action_name}' in folder '{folder.name}' "
                        f"-> Renamed action to '{action_name}'"
                    )
                else:
                    action_name = raw_action_name
                    skill_id = f"sk_{action_name}"

                seen_action_names.add(action_name)

                description = action_meta.get("description", "").strip()
                parameters = json.dumps(action_meta.get("parameters", {}))

                rows_to_insert.append((
                    skill_id,
                    action_name,
                    version,
                    category,
                    description,
                    parameters,
                    sys_reqs,
                    "[]",  # consumed_artifacts
                    "[]",  # produced_artifacts
                    str(plugin_path.resolve()),
                    handler_name,
                    "ACTIVE",
                    None,  # quarantine_reason
                    0,  # is_global
                ))

        except Exception as e:
            logger.error(f"Failed parsing {manifest_path}: {e}")

    logger.info(f"Preparing to write {len(rows_to_insert)} verified actions to {STATE_DB_PATH}")

    try:
        conn.execute("BEGIN TRANSACTION;")

        # Purge stale registry items before loading clean ground-truth state
        cursor.execute("DELETE FROM skill_registry;")

        cursor.executemany("""
            INSERT INTO skill_registry (
                skill_id, action_name, version, category, description,
                parameters, system_requirements, consumed_artifacts, produced_artifacts,
                entry_file_path, handler_name, status, quarantine_reason, is_global
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, rows_to_insert)

        conn.commit()

        print("\n" + "=" * 70)
        print(" 🎉 PASS 2 DATABASE REPAIR & SYNC COMPLETE")
        print("=" * 70)
        print(f" Total Folders Processed : {len(skill_folders)}")
        print(f" Actions Indexed into DB : {len(rows_to_insert)}")
        print(" Database Status         : ACTIVE & SYNCHRONIZED")
        print("=" * 70 + "\n")

    except Exception as e:
        conn.rollback()
        logger.error(f"Database repair transaction failed: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    sync_to_db()