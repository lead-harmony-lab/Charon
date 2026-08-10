#!/usr/bin/env python3
"""
scripts/repair_agent_skill_map.py
System Version: v0.6.7

Cleans orphaned skill mappings from agent_skill_map and resyncs
agent assignments from active manifests in skill_registry.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("~/Projects/Tools/Charon/charon/skills_registry/dynamic").expanduser()


def repair_and_resync_agent_map():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🧹 REPAIRING & RESYNCING `agent_skill_map`")
    print("=" * 70)

    # Step 1: Prune Orphaned Mappings
    cursor.execute("""
        DELETE FROM agent_skill_map 
        WHERE skill_id NOT IN (SELECT skill_id FROM skill_registry);
    """)
    pruned_count = cursor.rowcount
    print(f" 🗑️  Pruned {pruned_count} orphaned records from `agent_skill_map`.")

    # Step 2: Scan Manifests for Declared Agent Assignments
    new_mappings = []
    if SKILLS_DIR.exists():
        for m_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                skill_id = data.get("skill_id", m_path.parent.name)

                # Check for agent metadata key
                assigned_agent = (
                        data.get("agent_id")
                        or data.get("assigned_agent")
                        or data.get("target_agent")
                        or data.get("agent")
                )

                if assigned_agent:
                    # Confirm agent exists in agent_registry
                    cursor.execute(
                        "SELECT 1 FROM agent_registry WHERE agent_id = ?;", (assigned_agent,)
                    )
                    if cursor.fetchone():
                        # Confirm skill is in skill_registry
                        cursor.execute(
                            "SELECT 1 FROM skill_registry WHERE skill_id = ?;", (skill_id,)
                        )
                        if cursor.fetchone():
                            new_mappings.append((assigned_agent, skill_id))
            except Exception as e:
                print(f" ⚠️ Warning reading {m_path}: {e}")

    # Step 3: Insert Valid Manifest Mappings
    inserted_count = 0
    for agent_id, skill_id in new_mappings:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, (agent_id, skill_id))
        if cursor.rowcount > 0:
            inserted_count += 1

    conn.commit()

    # Step 4: Final Count
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_valid_mappings = cursor.fetchone()[0]

    print(f" ➕ Inserted {inserted_count} manifest-declared mappings.")
    print(f" ✅ Total Valid Mappings in DB: {total_valid_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    repair_and_resync_agent_map()