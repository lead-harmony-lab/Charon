import sqlite3
from pathlib import Path

# Adjust path to your Charon SQLite DB if necessary
db_path = Path("charon/data/charon.db")

if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Database Tables:", tables)

    # Inspect schema for permission-related tables
    for table in tables:
        tname = table[0]
        if "agent" in tname or "skill" in tname or "perm" in tname:
            print(f"\n--- Schema for {tname} ---")
            cursor.execute(f"PRAGMA table_info({tname});")
            for col in cursor.fetchall():
                print(col)