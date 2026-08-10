#!/usr/bin/env python3
"""
scripts/find_unindexed_skills.py
System Version: v0.6.0

Cross-references physical skill directory names against active/present entries
in skill_registry to report indexed vs. unindexed on-disk skills.
"""

import sqlite3
import sys
from pathlib import Path

# Standard database path fallback
STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()

GROUND_TRUTH_SKILLS = {
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


def find_unindexed():
    if not STATE_DB_PATH.exists():
        print(f"Error: Database file not found at {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT skill_id, action_name FROM skill_registry;")
    rows = cursor.fetchall()
    conn.close()

    indexed_in_db = set()
    for s_id, a_name in rows:
        if s_id:
            indexed_in_db.add(s_id)
        if a_name:
            indexed_in_db.add(a_name)

    indexed = GROUND_TRUTH_SKILLS.intersection(indexed_in_db)
    missing = GROUND_TRUTH_SKILLS - indexed_in_db

    print("=" * 65)
    print(f" 🟢 INDEXED SKILLS IN DATABASE ({len(indexed)} / 38)")
    print("=" * 65)
    for skill in sorted(indexed):
        print(f"  [✓] {skill}")

    print("\n" + "=" * 65)
    print(f" 🔴 UNINDEXED / MISSING SKILLS ({len(missing)} / 38)")
    print("=" * 65)
    for skill in sorted(missing):
        print(f"  [✗] {skill}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    find_unindexed()