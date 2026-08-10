import os
import json
import sqlite3
from pathlib import Path

# Paths based on your Charon environment
DB_PATH = os.path.expanduser("~/.local/share/charon/charon_state.db")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "charon", "agents")


def bootstrap_database():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("=== Initiating Clean Slate Protocol ===")
        # Disable foreign keys temporarily to allow unrestricted wiping of junk data
        cursor.execute("PRAGMA foreign_keys = OFF;")

        tables_to_purge = [
            "agent_skill_map",
            "skill_registry",
            "route_registry",
            "system_roles",
            "skill_gaps",
            "agent_registry"
        ]

        for table in tables_to_purge:
            cursor.execute(f"DELETE FROM {table};")
            print(f"Purged table: {table}")

        # Re-enable foreign keys for safe insertion
        cursor.execute("PRAGMA foreign_keys = ON;")

        print("\n=== Rebuilding Source of Truth ===")
        agent_specs = list(Path(AGENTS_DIR).rglob("staging/agent_spec.json"))

        if not agent_specs:
            print(f"No agent_spec.json files found in {AGENTS_DIR}/*/staging/")
            return

        for spec_path in agent_specs:
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)

            agent_id = spec.get("agent_id")
            display_name = spec.get("display_name")
            description = spec.get("description", "")
            default_action = spec.get("default_action", "idle")
            system_prompt = spec.get("system_prompt", "")
            role_name = spec.get("role_name")

            if not agent_id:
                print(f"Skipping {spec_path}: Missing 'agent_id'")
                continue

            print(f"Registering Agent: {display_name} ({agent_id})")

            # 1. Insert into agent_registry
            cursor.execute("""
                INSERT INTO agent_registry 
                (agent_id, display_name, description, default_action, system_prompt)
                VALUES (?, ?, ?, ?, ?)
            """, (agent_id, display_name, description, default_action, system_prompt))

            # 2. Insert into system_roles (if a role is defined)
            if role_name:
                print(f"  -> Assigning Role: {role_name}")
                cursor.execute("""
                    INSERT INTO system_roles (role_name, agent_id, description)
                    VALUES (?, ?, ?)
                """, (role_name, agent_id, f"Primary role for {display_name}"))

        conn.commit()
        print("\n=== Bootstrapping Complete ===")
        print("The database is clean. You are cleared to run 'reindex_skills'.")

    except Exception as e:
        conn.rollback()
        print(f"\nFailed during bootstrapping: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    bootstrap_database()