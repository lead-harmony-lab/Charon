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
CHARON_ROOT = Path("~/Projects/Tools/Charon/charon").expanduser()
LEGACY_AGENTS_DIR = CHARON_ROOT / "agents_delete"


def populate():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🛠️ POPULATING `agent_skill_map` (EXACT MATCH)")
    print("=" * 70)

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

    # 3. Load existing mappings to prevent duplication
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