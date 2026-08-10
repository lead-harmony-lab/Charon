#!/usr/bin/env python3
"""
scripts/relink_agent_skills_by_path.py

Rebuilds `agent_skill_map` by matching skill folders inside each agent's
staging directory to the `entry_file_path` column in `skill_registry`.
"""

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
CHARON_ROOT = Path("~/Projects/Tools/Charon/charon").expanduser()
AGENTS_DIR = CHARON_ROOT / "agents_delete"


def relink_agent_skills():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    if not AGENTS_DIR.exists():
        print(f"❌ Agents directory not found at: {AGENTS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🛠️ REBUILDING `agent_skill_map` VIA STAGING & ENTRY FILE PATHS")
    print("=" * 70)

    # 1. Map skill folders in DB to their respective skill_ids via entry_file_path
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry;")
    skill_rows = cursor.fetchall()

    folder_to_skill_ids = defaultdict(list)
    for skill_id, entry_file_path in skill_rows:
        if entry_file_path:
            folder_name = Path(entry_file_path).parent.name
            folder_to_skill_ids[folder_name].append(skill_id)

    print(f" ℹ️ DB holds {len(skill_rows)} total skills across {len(folder_to_skill_ids)} unique skill folders.")

    # 2. Fetch existing mappings to prevent any duplicates
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())
    print(f" ℹ️ Found {len(existing_mappings)} pre-existing mapping(s) in `agent_skill_map`.")

    # 3. Scan agents directory and match staging folders
    discovered_mappings = set()
    agents_processed = 0

    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue

        staging_dir = agent_dir / "staging"
        if not staging_dir.exists():
            continue

        # Resolve normalized agent_id from spec if available, fallback to folder name
        agent_id = agent_dir.name
        spec_file = staging_dir / "agent_spec.json"
        if spec_file.exists():
            try:
                spec_data = json.loads(spec_file.read_text(encoding="utf-8"))
                agent_id = spec_data.get("agent_id", agent_id)
            except Exception:
                pass

        agents_processed += 1
        agent_linked_count = 0

        # Scan subdirectories inside staging/
        for skill_folder in staging_dir.iterdir():
            if skill_folder.is_dir():
                folder_name = skill_folder.name

                # Match staging folder name against skill_registry folder paths
                matched_skill_ids = folder_to_skill_ids.get(folder_name, [])
                for skill_id in matched_skill_ids:
                    discovered_mappings.add((agent_id, skill_id))
                    agent_linked_count += 1

        print(f"  • Agent [{agent_id}]: Matched {agent_linked_count} skill action bindings.")

    # 4. Deduplicate against current DB state
    new_mappings = discovered_mappings - existing_mappings

    # 5. Insert recovered mappings
    if new_mappings:
        cursor.executemany("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, list(new_mappings))
        conn.commit()

    # 6. Final Status Audit
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print(f" 👥 Agents Scanned       : {agents_processed}")
    print(f" ➕ New Mappings Added  : {len(new_mappings)}")
    print(f" ✅ Total Valid Mappings: {total_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    relink_agent_skills()