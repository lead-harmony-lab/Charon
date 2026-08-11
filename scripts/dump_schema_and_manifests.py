#!/usr/bin/env python3
"""
scripts/dump_schema_and_manifests.py
System Version: v0.6.4 (Read-Only)

Dumps:
1. Current SQLite table schema for 'skill_registry'
2. Raw manifest.json contents for 3 representative skills
"""

import json
import sqlite3
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

SAMPLES = [
    "archivist_datasheet_rag",
    "archivist_vector_ledger",
    "code_python_interpreter",
]


def dump_info():
    print("\n" + "=" * 80)
    print(" 🏛️  1. CURRENT DATABASE SCHEMA (`skill_registry`)")
    print("=" * 80)

    if STATE_DB_PATH.exists():
        conn = sqlite3.connect(str(STATE_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(skill_registry);")
        columns = cursor.fetchall()
        conn.close()

        print(f"{'CID':<5} | {'COLUMN NAME':<25} | {'DATA TYPE':<12} | {'NOT NULL':<8} | {'DEFAULT'}")
        print("-" * 80)
        for col in columns:
            cid, name, type_, notnull, dflt, pk = col
            print(f"{cid:<5} | {name:<25} | {type_:<12} | {notnull:<8} | {dflt}")
    else:
        print(f"⚠️ Database not found at {STATE_DB_PATH}")

    print("\n" + "=" * 80)
    print(" 📄 2. RAW SAMPLE MANIFESTS FROM DISK")
    print("=" * 80)

    for sample in SAMPLES:
        m_path = SKILLS_DIR / sample / "manifest.json"
        print(f"\n--- 📁 {sample}/manifest.json ---")
        if m_path.exists():
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                print(json.dumps(content, indent=2))
            except Exception as e:
                print(f"Error reading JSON: {e}")
        else:
            print("⚠️ File not found.")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    dump_info()