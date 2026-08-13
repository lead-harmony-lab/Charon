import sqlite3
import sys
from pathlib import Path

# Resolve path based on your environment
DB_PATH = Path.home() / ".local" / "share" / "charon" / "charon_state.db"

def run_fix():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("🛡️  Starting agent_registry schema fix...")

    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    cursor = conn.cursor()

    try:
        # Step 1: Disable foreign keys
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("BEGIN TRANSACTION;")

        # Step 2: Create the correct agent_registry table (No default_skill_id)
        print("🏗️  Building corrected agent_registry table...")
        cursor.execute("""
            CREATE TABLE agent_registry_new (
                agent_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL,
                default_action TEXT,    -- Sole link to skill_registry
                system_prompt TEXT DEFAULT '',
                priority_weight REAL DEFAULT 1.0,
                override_triggers TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                -- Single correct Foreign Key mapping to the action
                FOREIGN KEY(default_action) REFERENCES skill_registry(action_name) 
                    ON UPDATE CASCADE ON DELETE SET NULL
            );
        """)

        # Step 3: Migrate data and drop the hallucinated column
        print("🧬 Migrating data and purging 'default_skill_id'...")
        cursor.execute("""
            INSERT INTO agent_registry_new (
                agent_id, display_name, description, default_action,
                system_prompt, priority_weight, override_triggers, is_active, created_at, updated_at
            )
            SELECT 
                agent_id, display_name, description, default_action, 
                system_prompt, priority_weight, override_triggers, is_active, created_at, updated_at
            FROM agent_registry;
        """)

        # Step 4: Temporarily drop triggers attached to OTHER tables that reference agent_registry
        print("🔪 Unhooking dependent triggers...")
        cursor.execute("DROP TRIGGER IF EXISTS prevent_inactive_agent_role_assignment;")
        cursor.execute("DROP TRIGGER IF EXISTS prevent_mandatory_role_agent_deactivation;")

        # Step 5: Swap the tables
        print("🔄 Swapping tables...")
        cursor.execute("DROP TABLE agent_registry;")
        cursor.execute("ALTER TABLE agent_registry_new RENAME TO agent_registry;")

        # Step 6: Recreate dropped indexes and triggers
        print("⚡ Re-attaching triggers and indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_registry_is_active ON agent_registry(is_active);")

        cursor.execute("""
            CREATE TRIGGER prevent_mandatory_role_agent_deactivation
            BEFORE UPDATE OF is_active ON agent_registry
            WHEN NEW.is_active = 0
            BEGIN
              SELECT CASE
                WHEN EXISTS (
                  SELECT 1 FROM system_roles
                  WHERE agent_id = NEW.agent_id AND is_mandatory = 1
                )
                THEN RAISE(ABORT, 'Operation blocked: Cannot deactivate an agent bound to a mandatory system role.')
              END;
            END;
        """)

        cursor.execute("""
            CREATE TRIGGER prevent_inactive_agent_role_assignment
            BEFORE UPDATE OF agent_id ON system_roles
            WHEN NEW.agent_id IS NOT NULL
            BEGIN
              SELECT CASE
                WHEN (SELECT is_active FROM agent_registry WHERE agent_id = NEW.agent_id) = 0
                THEN RAISE(ABORT, 'Operation blocked: Cannot assign an inactive agent to a system role.')
              END;
            END;
        """)

        # Step 7: Commit transaction
        cursor.execute("COMMIT;")
        print("✅ Schema fix complete! 'default_skill_id' is gone and the codebase constraints are restored.")

    except Exception as e:
        cursor.execute("ROLLBACK;")
        print(f"❌ Fix failed. Rolling back all changes. Error: {e}")
    finally:
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.close()

if __name__ == "__main__":
    run_fix()