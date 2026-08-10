#!/usr/bin/env python3
"""
scripts/verify_db_disk_sync.py
System Version: v0.6.7

Audit Script:
Verifies that 100% of the skills registered in SQLite exist physically on disk
and checks for any orphaned records or non-existent file paths.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("~/Projects/Tools/Charon/charon/skills_registry/dynamic").expanduser()


def audit_db_against_disk():
    if not STATE_DB_PATH.exists():
        print(f"❌ ERROR: Database missing at {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # Get all tables in the DB
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    print("\n" + "=" * 70)
    print(" 🔍 CHARON DATABASE -> DISK SYNC AUDIT")
    print("=" * 70)
    print(f" Database Path : {STATE_DB_PATH}")
    print(f" Tables Found  : {', '.join(tables)}")
    print("=" * 70)

    # 1. Inspect skill_registry table
    cursor.execute("""
        SELECT skill_id, action_name, entry_file_path, status 
        FROM skill_registry;
    """)
    rows = cursor.fetchall()

    missing_paths = []
    missing_manifest_actions = []
    active_count = 0

    for skill_id, action_name, entry_file_path, status in rows:
        if status == "ACTIVE":
            active_count += 1

        path = Path(entry_file_path)

        # Check if plugin.py exists
        if not path.exists():
            missing_paths.append((skill_id, action_name, entry_file_path))
            continue

        # Check if manifest exists in parent folder and contains an action
        manifest_path = path.parent / "manifest.json"
        if not manifest_path.exists():
            missing_manifest_actions.append((skill_id, "Missing manifest.json"))
            continue

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            supported_actions = manifest_data.get("supported_actions", {})

            # Match either exact action_name or handler (for renamed collisions)
            action_found = any(
                act == action_name or f"{path.parent.name}_{act}" == action_name
                for act in supported_actions
            )

            if not action_found:
                missing_manifest_actions.append((skill_id, f"Action '{action_name}' not in {manifest_path}"))
        except Exception as e:
            missing_manifest_actions.append((skill_id, f"Invalid manifest JSON: {e}"))

    # Summary Report
    print(f" Total Rows in DB       : {len(rows)}")
    print(f" Active Actions         : {active_count}")
    print(f" Orphaned Paths (No Py) : {len(missing_paths)}")
    print(f" Manifest Discrepancies : {len(missing_manifest_actions)}")
    print("-" * 70)

    if missing_paths:
        print("\n❌ ORPHANED DB RECORDS (File Missing):")
        for sid, act, pth in missing_paths:
            print(f"  - [{sid}] {act} -> {pth}")

    if missing_manifest_actions:
        print("\n❌ MANIFEST MISMATCHES:")
        for sid, err in missing_manifest_actions:
            print(f"  - [{sid}] {err}")

    if not missing_paths and not missing_manifest_actions:
        print(" SUCCESS: 100% of database records match physical files on disk!")
        print(" ZERO ghost skills detected.")
        print("=" * 70 + "\n")
    else:
        print("\n⚠️ AUDIT FAILED: Discrepancies detected between DB and Disk.")
        print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    audit_db_against_disk()