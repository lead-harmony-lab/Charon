import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "charon" / "charon_state.db"

# Direct alignment map: legacy action_name -> updated action_name
ACTION_MAPPING = {
    "search_web": "web_search_execute",
    "compile_firmware": "execution_hw_compile",
    "answer_query": "execution_generalist_answer",
    "inspect_cad_files": "execution_fab_inspect",
    "check_inventory": "data_quartermaster_check",
    "get_system_health": "system_sys_analyze",
    "solve_edge_case": "autonomous_code_solve",
    "draft_build_sequence": "autonomous_plan_draft",
    "read_sensor_net": "execution_iot_read",
    "list_workspaces": "system_cleaner_list",
}

def sync_default_actions():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("BEGIN TRANSACTION;")

        print("🔄 Mapping legacy default actions...")
        for old_action, new_action in ACTION_MAPPING.items():
            cursor.execute(
                "UPDATE agent_registry SET default_action = ? WHERE default_action = ?;",
                (new_action, old_action)
            )

        # Clear any remaining default_action values that still don't exist in skill_registry
        print("🧹 Nullifying unresolvable default actions...")
        cursor.execute("""
            UPDATE agent_registry 
            SET default_action = NULL 
            WHERE default_action IS NOT NULL 
              AND default_action NOT IN (SELECT action_name FROM skill_registry);
        """)

        cursor.execute("COMMIT;")
        print("✅ Default actions synchronized successfully!")

    except Exception as e:
        cursor.execute("ROLLBACK;")
        print(f"❌ Synchronization failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    sync_default_actions()