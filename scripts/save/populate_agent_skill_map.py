#!/usr/bin/env python3
"""
scripts/populate_agent_skill_map.py

Exact mapping:
1. Agent ID = folder name in charon/agents_delete/
2. Skill Folder = subfolder in charon/agents_delete/<agent_id>/staging/skills/
3. Skill ID = matches folder name in skill_registry.entry_file_path
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()

# Dynamically resolve the project root based on this script's location
# (Works whether the script is in /scripts or /scripts/save)
current_dir = Path(__file__).resolve().parent
CHARON_ROOT = current_dir
while CHARON_ROOT.name != 'Charon' and CHARON_ROOT.parent != CHARON_ROOT:
    CHARON_ROOT = CHARON_ROOT.parent

# Fallback just in case the dynamic resolution misses
if CHARON_ROOT.name != 'Charon':
    CHARON_ROOT = Path("~/Projects/Tools/Charon").expanduser()

# Fixed path: pointing into the inner 'charon' module directory
LEGACY_AGENTS_DIR = CHARON_ROOT / "charon" / "agents_delete"

# Path migration variables
OLD_STORAGE_DIR = "charon/skill_registry"
NEW_STORAGE_DIR = "charon/cli/librarian/storage"


def populate():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    if not LEGACY_AGENTS_DIR.exists():
        print(f"❌ Legacy agents directory not found at: {LEGACY_AGENTS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🛠️ POPULATING `agent_skill_map` (EXACT MATCH)")
    print("=" * 70)

    # 0. Self-Healing: Migrate legacy paths in the database if any remain
    cursor.execute(
        "UPDATE skill_registry "
        "SET entry_file_path = REPLACE(entry_file_path, ?, ?) "
        "WHERE entry_file_path LIKE ?;",
        (OLD_STORAGE_DIR, NEW_STORAGE_DIR, f"%{OLD_STORAGE_DIR}%")
    )
    if cursor.rowcount > 0:
        print(f" 🩹 Migrated {cursor.rowcount} legacy skill paths to new librarian storage.")
        conn.commit()

    # 0.5. Clean Slate: Purge the old junk mappings
    print(" 🧹 Purging existing 'junk' mappings to start fresh...")
    cursor.execute("DELETE FROM agent_skill_map;")
    conn.commit()

    # 1. Load exact valid agent IDs from agent_registry
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    # 2. Map skill folder names to skill_ids via entry_file_path in skill_registry
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry;")
    folder_to_skills = defaultdict(list)
    for skill_id, entry_path in cursor.fetchall():
        if entry_path:
            folder_name = Path(entry_path).parent.name
            folder_to_skills[folder_name].append(skill_id)

    # 3. Load existing mappings (This will be empty now, but kept for script integrity)
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())

    print(f" ℹ️ DB holds {len(valid_agents)} Agents and {len(folder_to_skills)} Skill Folders.")
    print(f" ℹ️ Existing mappings in `agent_skill_map`: {len(existing_mappings)}")

    new_mappings = set()

    # 4. Scan agents_delete directories directly
    for agent_dir in sorted(LEGACY_AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue

        agent_id = agent_dir.name  # Exact match to agent_registry (e.g., 'archivist')
        if agent_id not in valid_agents:
            continue

        skills_dir = agent_dir / "staging" / "skills"
        if not skills_dir.exists():
            continue

        agent_count = 0
        for skill_folder in skills_dir.iterdir():
            if not skill_folder.is_dir():
                continue

            folder_name = skill_folder.name
            matched_skill_ids = folder_to_skills.get(folder_name, [])

            for skill_id in matched_skill_ids:
                mapping_pair = (agent_id, skill_id)
                if mapping_pair not in existing_mappings:
                    new_mappings.add(mapping_pair)
                    agent_count += 1

        if agent_count > 0:
            print(f"  • Agent [{agent_id}]: Queued {agent_count} new skill mapping(s)")

    # 5. Insert new unique mappings
    if new_mappings:
        cursor.executemany("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, list(new_mappings))
        conn.commit()

    # 6. Report final database status
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_count = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print(f" ➕ New Mappings Added  : {len(new_mappings)}")
    print(f" ✅ Total Valid Mappings: {total_count}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    populate()