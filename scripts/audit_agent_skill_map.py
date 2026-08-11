#!/usr/bin/env python3
"""
scripts/audit_agent_skill_map.py
System Version: v0.6.7

Audits agent skill mappings by comparing physical manifest metadata against
agent_registry, skill_registry, and agent_skill_map in SQLite.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def audit_agent_skill_mappings():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # 1. Fetch registered agents
    cursor.execute("SELECT agent_id, display_name, is_active FROM agent_registry;")
    agents = {row[0]: {"display_name": row[1], "is_active": row[2]} for row in cursor.fetchall()}

    # 2. Fetch registered skills
    cursor.execute("SELECT skill_id, action_name, status FROM skill_registry;")
    db_skills = {row[0]: {"action_name": row[1], "status": row[2]} for row in cursor.fetchall()}

    # 3. Fetch agent_skill_map
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    db_map = cursor.fetchall()

    # 4. Read Manifest files for disk-side agent references
    manifest_agent_refs = {}
    if SKILLS_DIR.exists():
        for m_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                s_id = data.get("skill_id", m_path.parent.name)
                declared_agent = (
                    data.get("agent_id")
                    or data.get("assigned_agent")
                    or data.get("target_agent")
                    or data.get("agent")
                    or data.get("role")
                )
                manifest_agent_refs[s_id] = declared_agent
            except Exception:
                pass

    print("\n" + "=" * 70)
    print(" 🤖 CHARON AGENT <-> SKILL MAP AUDIT")
    print("=" * 70)

    # Agent Summary
    print(f"\n📋 REGISTERED AGENTS IN `agent_registry` ({len(agents)} Total):")
    for a_id, info in agents.items():
        status_str = "ACTIVE" if info["is_active"] else "INACTIVE"
        print(f"  • [{a_id}] ({info['display_name']}) -> {status_str}")

    # Outdated Agents Check
    invalid_agents_in_map = [row for row in db_map if row[0] not in agents]
    invalid_skills_in_map = [row for row in db_map if row[1] not in db_skills]

    print(f"\n🔗 DB `agent_skill_map` RECORDS ({len(db_map)} Total Mappings):")
    if invalid_agents_in_map:
        print(f"\n⚠️ OUTDATED / UNREGISTERED AGENT IDs IN `agent_skill_map` ({len(invalid_agents_in_map)}):")
        for a_id, s_id in invalid_agents_in_map:
            print(f"  ❌ Agent ID '{a_id}' mapped to Skill '{s_id}' (Agent missing from agent_registry)")
    else:
        print("  ✅ All mapped `agent_id` records match valid agents in `agent_registry`.")

    if invalid_skills_in_map:
        print(f"\n⚠️ UNINDEXED / MISSING SKILL IDs IN `agent_skill_map` ({len(invalid_skills_in_map)}):")
        for a_id, s_id in invalid_skills_in_map:
            print(f"  ❌ Skill ID '{s_id}' mapped to Agent '{a_id}' (Skill missing from skill_registry)")
    else:
        print("  ✅ All mapped `skill_id` records match valid skills in `skill_registry`.")

    # Manifest vs DB Mapping Discrepancies
    discrepancies = []
    for s_id, decl_agent in manifest_agent_refs.items():
        if decl_agent:
            mapped_agents = [a_id for a_id, skill in db_map if skill == s_id]
            if decl_agent not in mapped_agents:
                discrepancies.append((s_id, decl_agent, mapped_agents))

    if discrepancies:
        print(f"\n⚠️ MANIFEST DECLARATION VS DB MAPPING DISCREPANCIES ({len(discrepancies)}):")
        for s_id, decl_agent, mapped_agents in discrepancies:
            print(f"  - Skill: '{s_id}'")
            print(f"    • Manifest Specifies : '{decl_agent}'")
            print(f"    • DB Map Contains    : {mapped_agents if mapped_agents else 'NONE'}")
    else:
        print("  ✅ No manifest-to-database agent assignment conflicts detected.")

    print("\n" + "=" * 70 + "\n")
    conn.close()


if __name__ == "__main__":
    audit_agent_skill_mappings()