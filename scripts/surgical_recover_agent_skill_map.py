#!/usr/bin/env python3
"""
scripts/surgical_recover_agent_skill_map.py

Non-destructive recovery tool for agent_skill_map.
Scans disk manifests and agent specs to restore capability links into SQLite.
Guarantees zero duplication of existing mappings.
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
CHARON_ROOT = Path("~/Projects/Tools/Charon/charon").expanduser()
SKILLS_DIR = CHARON_ROOT / "storage" / "dynamic"
AGENTS_DIR = CHARON_ROOT / "agents"


def recover_agent_skill_map():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🩹 SURGICAL RECOVERY: `agent_skill_map`")
    print("=" * 70)

    # 1. Fetch existing state from DB (Read-Only)
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT skill_id, action_name FROM skill_registry;")
    skill_rows = cursor.fetchall()
    valid_skills = {row[0] for row in skill_rows}
    action_to_skill = {row[1]: row[0] for row in skill_rows}

    # Fetch existing mappings to prevent any duplicates
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())

    print(f" ℹ️ DB holds {len(valid_agents)} Agents and {len(valid_skills)} Skills.")
    print(f" ℹ️ Found {len(existing_mappings)} existing mapping(s) in `agent_skill_map`.")

    scanned_mappings = set()

    # 2. PASS A: Scan Agent Specs (Agent -> Skills/Actions)
    if AGENTS_DIR.exists():
        for spec_path in AGENTS_DIR.rglob("*.json"):
            try:
                data = json.loads(spec_path.read_text(encoding="utf-8"))
                agent_id = data.get("agent_id")
                if not agent_id or agent_id not in valid_agents:
                    continue

                declared_items = []
                for key in ("skills", "actions", "capabilities", "equipped_skills"):
                    val = data.get(key)
                    if isinstance(val, list):
                        declared_items.extend(val)

                for item in declared_items:
                    if item in valid_skills:
                        scanned_mappings.add((agent_id, item))
                    elif item in action_to_skill:
                        scanned_mappings.add((agent_id, action_to_skill[item]))

            except Exception as e:
                print(f" ⚠️ Warning reading agent spec {spec_path}: {e}")

    # 3. PASS B: Scan Skill Manifests (Skill -> Agent)
    if SKILLS_DIR.exists():
        for manifest_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                skill_id = data.get("skill_id", manifest_path.parent.name)

                if skill_id not in valid_skills:
                    continue

                agent_refs = []
                for key in ("agent_id", "assigned_agent", "target_agent", "agent", "role"):
                    val = data.get(key)
                    if isinstance(val, str):
                        agent_refs.append(val)
                    elif isinstance(val, list):
                        agent_refs.extend(val)

                for a_id in agent_refs:
                    if a_id in valid_agents:
                        scanned_mappings.add((a_id, skill_id))

            except Exception as e:
                print(f" ⚠️ Warning reading skill manifest {manifest_path}: {e}")

    # 4. Filter out any mapping that already exists in the table
    new_mappings = scanned_mappings - existing_mappings

    if not new_mappings:
        print(" ✨ No new unique mappings found to insert.")
    else:
        # Safely insert only genuinely new bindings
        for agent_id, skill_id in new_mappings:
            cursor.execute("""
                INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?);
            """, (agent_id, skill_id))

        conn.commit()

    # 5. Report Final State
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    print(f" ➕ Inserted {len(new_mappings)} new unique map records.")
    print(f" ✅ Total Active Mappings in DB: {total_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    recover_agent_skill_map()