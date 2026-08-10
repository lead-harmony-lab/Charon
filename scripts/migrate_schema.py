#!/usr/bin/env python3
import json
import logging
import sqlite3
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("Charon.Migration")

DB_PATH = Path.home() / ".local" / "share" / "charon" / "charon_state.db"


def migrate_database():
    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return

    logger.info(f"Connecting to database at {DB_PATH}")

    # Connect with dictionary-like row access
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Enable foreign keys (though we will turn them off briefly for the table swap)
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # ---------------------------------------------------------
        # 1. Clean Up Redundant Tables
        # ---------------------------------------------------------
        logger.info("Dropping redundant 'agents' table...")
        cursor.execute("DROP TABLE IF EXISTS agents;")

        # ---------------------------------------------------------
        # 2. Rebuild skill_registry & Populate agent_skill_map
        # ---------------------------------------------------------
        logger.info("Rebuilding 'skill_registry' and extracting manifest data...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_registry_new (
                action_name TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                category TEXT DEFAULT 'General',
                description TEXT NOT NULL DEFAULT '',
                parameters TEXT DEFAULT '{}',
                system_requirements TEXT NOT NULL DEFAULT '[]',
                consumed_artifacts TEXT NOT NULL DEFAULT '[]',
                produced_artifacts TEXT NOT NULL DEFAULT '[]',
                entry_file_path TEXT NOT NULL,
                handler_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_global INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Fetch all existing skills
        cursor.execute("SELECT * FROM skill_registry;")
        existing_skills = cursor.fetchall()

        for skill in existing_skills:
            action_name = skill["action_name"]
            manifest_raw = skill["manifest_json"]

            # Parse manifest_json to determine global status and specific shelf tags
            is_global = 0
            shelf_tags = []

            if manifest_raw:
                try:
                    manifest_data = json.loads(manifest_raw)
                    shelf_tags = manifest_data.get("shelf_tags", [])
                    primary_agent = manifest_data.get("primary_agent_id")

                    if primary_agent and primary_agent not in shelf_tags:
                        shelf_tags.append(primary_agent)

                    if "*" in shelf_tags:
                        is_global = 1
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse manifest JSON for action '{action_name}'. Defaulting to global.")
                    is_global = 1

            # Insert into the new refined table
            cursor.execute("""
                INSERT INTO skill_registry_new (
                    action_name, skill_id, version, category, description, 
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, 
                    is_active, is_global, indexed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_name, skill["skill_id"], skill["version"], skill["category"],
                skill["description"], skill["parameters"], skill["system_requirements"],
                skill["consumed_artifacts"], skill["produced_artifacts"],
                skill["entry_file_path"], skill["handler_name"], skill["is_active"],
                is_global, skill["indexed_at"], skill["updated_at"]
            ))

            # Populate agent_skill_map for non-global agents explicitly listed
            if not is_global:
                for tag in shelf_tags:
                    if tag != "*":
                        cursor.execute("""
                            INSERT OR IGNORE INTO agent_skill_map (agent_id, action_name) 
                            VALUES (?, ?)
                        """, (tag, action_name))

        # Swap the skills tables
        cursor.execute("DROP TABLE skill_registry;")
        cursor.execute("ALTER TABLE skill_registry_new RENAME TO skill_registry;")
        cursor.execute("CREATE INDEX idx_skill_registry_action ON skill_registry(action_name);")

        # ---------------------------------------------------------
        # 3. Upgrade system_roles to use RESTRICT
        # ---------------------------------------------------------
        logger.info("Upgrading 'system_roles' table constraints...")

        cursor.execute("""
            CREATE TABLE system_roles_new (
                role_name TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
            );
        """)

        # Copy existing roles
        cursor.execute("INSERT INTO system_roles_new SELECT * FROM system_roles;")

        # Swap the roles tables
        cursor.execute("DROP TABLE system_roles;")
        cursor.execute("ALTER TABLE system_roles_new RENAME TO system_roles;")
        cursor.execute("CREATE INDEX idx_system_roles_agent ON system_roles(agent_id);")

        # ---------------------------------------------------------
        # Commit & Re-enable Pragmas
        # ---------------------------------------------------------
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        logger.info("Migration completed successfully. The database schema is now unified.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}. Changes rolled back.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()