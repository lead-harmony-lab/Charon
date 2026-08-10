#!/usr/bin/env python3
"""
scripts/audit_and_purge_skills.py
System Version: v0.6.1

Audit and database purging tool to inspect skill_registry for AI-hallucinated skills
and clean up orphan/ghost entries across skill_registry, agent_skill_map,
skill_gaps, and skill_permissions safely with dynamic schema introspection.
"""

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Set

# Standard Charon Config Path Fallback
try:
    from charon.config.paths import STATE_DB_PATH
except ImportError:
    STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.Maintenance.PurgeSkills")

# Ground Truth List of 38 Verified On-Disk Skill Directory Names
GROUND_TRUTH_SKILLS: Set[str] = {
    "archivist_datasheet_rag",
    "archivist_vector_ledger",
    "cleaner_cad_sweeper",
    "cleaner_git_manager",
    "cleaner_log_pruner",
    "cleaner_workspace_deleter",
    "cleaner_workspace_inspector",
    "cleaner_workspace_scaffolder",
    "code_python_interpreter",
    "code_sandbox_executor",
    "code_script_generator",
    "code_self_healing_solver",
    "extract_pdf_ocr_skill",
    "fab_cad_tools",
    "fab_cam_slicer",
    "fab_printer_transmitter",
    "generalist_math_evaluator",
    "generalist_query_handler",
    "generalist_rag_synthesizer",
    "generalist_system_executor",
    "generalist_system_inspector",
    "hw_eda_kicad",
    "hw_firmware_pio",
    "iot_home_assistant",
    "iot_mqtt_publisher",
    "kicad_bom_exporter",
    "plan_task_decomposer",
    "quartermaster_bom_auditor",
    "quartermaster_datasheet_fetcher",
    "quartermaster_inventory_manager",
    "skill_builder",
    "sys_asset_pruner",
    "sys_health_auditor",
    "sys_log_analyzer",
    "sys_os_control",
    "task_tracker_manage",
    "web_scraper",
    "web_search",
}


def get_table_columns(cursor: sqlite3.Cursor, table_name: str) -> Set[str]:
    """Helper to dynamically fetch column names for a table."""
    try:
        cursor.execute(f"PRAGMA table_info({table_name});")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()


def audit_and_purge_db(db_path: Path, dry_run: bool = False) -> None:
    """Audits skill_registry against ground-truth and purges invalid/hallucinated rows across all linked tables."""
    if not db_path.exists():
        logger.error(f"Database file not found at: {db_path}")
        sys.exit(1)

    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # 1. Fetch current database state
        cursor.execute("SELECT * FROM skill_registry;")
        rows = cursor.fetchall()

        valid_skills: List[Dict] = []
        hallucinated_skills: List[Dict] = []

        for row in rows:
            r_dict = dict(row)
            skill_id = r_dict.get("skill_id", "")
            action_name = r_dict.get("action_name", "")

            # Check if skill matches ground truth either by ID or action name
            if skill_id in GROUND_TRUTH_SKILLS or action_name in GROUND_TRUTH_SKILLS:
                valid_skills.append(r_dict)
            else:
                hallucinated_skills.append(r_dict)

        # 2. Display Audit Summary
        print("\n" + "=" * 80)
        print(" 📊 SKILL REGISTRY AUDIT REPORT")
        print("=" * 80)
        print(f" Total Registered Skills in DB : {len(rows)}")
        print(f" Verified / Valid Skills On-Disk: {len(valid_skills)}")
        print(f" Hallucinated / Ghost Skills    : {len(hallucinated_skills)}")
        print("=" * 80 + "\n")

        if not hallucinated_skills:
            logger.info("✨ Database is clean! No hallucinated skills detected.")
            return

        print("🚨 HALLUCINATED / GHOST SKILLS TO BE PURGED:")
        print("-" * 80)
        print(f"{'SKILL ID':<35} | {'ACTION NAME':<30} | {'STATUS':<10}")
        print("-" * 80)

        junk_ids: Set[str] = set()
        junk_actions: Set[str] = set()

        for junk in hallucinated_skills:
            s_id = junk.get("skill_id", "")
            a_name = junk.get("action_name", "")
            status = junk.get("status", "")

            if s_id:
                junk_ids.add(s_id)
            if a_name:
                junk_actions.add(a_name)

            print(f"{s_id:<35} | {a_name:<30} | {status:<10}")

        print("-" * 80 + "\n")

        if dry_run:
            logger.info("🔍 Dry-run mode enabled. No changes were committed.")
            return

        # 3. Perform Dynamic Atomic Purge
        logger.info("Starting multi-table atomic purge with dynamic schema matching...")
        conn.execute("BEGIN TRANSACTION;")

        deleted_counts: Dict[str, int] = {}
        all_junk_terms = list(junk_ids.union(junk_actions))

        # Helper function for safe conditional table deletion
        def safe_delete_from_table(table_name: str, target_fields: List[str]) -> int:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
            if not cursor.fetchone():
                return 0

            existing_cols = get_table_columns(cursor, table_name)
            matched_cols = [col for col in target_fields if col in existing_cols]

            if not matched_cols:
                return 0

            ph = ",".join("?" * len(all_junk_terms))
            where_conditions = [f"{col} IN ({ph})" for col in matched_cols]
            sql = f"DELETE FROM {table_name} WHERE {' OR '.join(where_conditions)};"

            # Multiply parameter tuple for each matched column condition
            params = all_junk_terms * len(matched_cols)
            cursor.execute(sql, params)
            return cursor.rowcount

        # Execute safe dynamic purge across linked tables
        deleted_counts["skill_permissions"] = safe_delete_from_table("skill_permissions", ["skill_id", "perm_id"])
        deleted_counts["agent_skill_map"] = safe_delete_from_table("agent_skill_map", ["skill_id", "agent_id"])
        deleted_counts["skill_gaps"] = safe_delete_from_table("skill_gaps",
                                                              ["skill_id", "action_name", "required_skill",
                                                               "missing_skill"])
        deleted_counts["skill_registry"] = safe_delete_from_table("skill_registry", ["skill_id", "action_name"])

        conn.commit()

        print("=" * 80)
        print(" 🧹 CLEANUP COMPLETE")
        print("=" * 80)
        for tbl, count in deleted_counts.items():
            print(f" Removed from '{tbl}': {count} records")
        print("=" * 80 + "\n")
        logger.info("Database state successfully synchronized with physical filesystem.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to purge database! Transaction rolled back. Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit and purge hallucinated skills from state.db")
    parser.add_argument("--db", type=str, default=str(STATE_DB_PATH), help="Path to state.db")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without deleting")
    args = parser.parse_args()

    audit_and_purge_db(Path(args.db), dry_run=args.dry_run)