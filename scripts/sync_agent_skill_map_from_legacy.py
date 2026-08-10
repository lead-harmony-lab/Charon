#!/usr/bin/env python3
"""
scripts/sync_agent_skill_map_from_legacy.py
System Version: v0.6.7

Restores agent_skill_map associations by matching legacy folder paths in
charon/agents_delete/{agent_id}/staging/skills/{folder_name}
against entry_file_path in skill_registry.
"""

import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
LEGACY_AGENTS_DIR = Path("~/Projects/Tools/Charon/charon/agents_delete").expanduser()


def sync_mappings_from_legacy_tree():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    if not LEGACY_AGENTS_DIR.exists():
        print(f"❌ Legacy directory not found: {LEGACY_AGENTS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # 1. Fetch valid agent IDs
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    # 2. Fetch active skills from skill_registry with entry_file_path
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry WHERE status = 'ACTIVE';")
    active_skills_db = cursor.fetchall()

    # Build folder_name -> list of skill_ids mapping
    folder_to_skill_ids = {}
    for skill_id, entry_file_path in active_skills_db:
        folder_name = Path(entry_file_path).parent.name
        if folder_name not in folder_to_skill_ids:
            folder_to_skill_ids[folder_name] = []
        folder_to_skill_ids[folder_name].append(skill_id)

    print("\n" + "=" * 70)
    print(" 📂 RESTORING AGENT-SKILL MAPPINGS VIA PATH MATCHING")
    print("=" * 70)
    print(f" Legacy Source Directory: {LEGACY_AGENTS_DIR}\n")

    mappings_to_insert = []
    unmatched_folders = []

    # 3. Crawl agents_delete/{agent_id}/staging/skills/{folder_name}
    for agent_dir in LEGACY_AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue

        agent_id = agent_dir.name
        if agent_id not in valid_agents:
            print(f" ⚠️ Skipping unknown agent directory: '{agent_id}'")
            continue

        skills_dir = agent_dir / "staging" / "skills"
        if not skills_dir.exists():
            continue

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue

            folder_name = skill_dir.name

            if folder_name in folder_to_skill_ids:
                for skill_id in folder_to_skill_ids[folder_name]:
                    mappings_to_insert.append((agent_id, skill_id))
            else:
                unmatched_folders.append((agent_id, folder_name))

    # 4. Insert mappings into DB
    inserted_count = 0
    for agent_id, skill_id in mappings_to_insert:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, (agent_id, skill_id))
        if cursor.rowcount > 0:
            inserted_count += 1

    conn.commit()

    # 5. Final summary
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT skill_id) FROM agent_skill_map;")
    mapped_skills_count = cursor.fetchone()[0]

    print(f" ✅ Restored Mappings     : {inserted_count} new entries inserted")
    print(f" 🔗 Total Active Mappings : {total_mappings}")
    print(f" 🎯 Unique Skills Assigned : {mapped_skills_count} / {len(active_skills_db)}")

    if unmatched_folders:
        print("\n ⚠️ Unmatched Skill Folders (Not active in skill_registry):")
        for a_id, f_id in unmatched_folders:
            print(f"    - Agent '{a_id}' -> Folder '{f_id}'")

    print("=" * 70 + "\n")
    conn.close()


if __name__ == "__main__":
    sync_mappings_from_legacy_tree()