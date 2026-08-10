#!/usr/bin/env python3
import sqlite3
import os
from pathlib import Path

DB_PATH = os.path.expanduser("~/.local/share/charon/charon_state.db")

# Keyword heuristics for matching skills to permission primitives
HEURISTICS = {
    "sys:shell_exec": ["exec", "shell", "bash", "terminal", "command", "run_script", "process", "cli"],
    "net:http_request": ["http", "web", "url", "api", "fetch", "download", "scrape", "search", "request"],
    "fs:write_file": ["write", "save", "create_file", "append", "edit_file", "output_file", "store"],
    "fs:read_file": ["read", "cat", "get_file", "load", "parse", "view", "inspect", "search_file"]
}

def seed_skill_permissions():
    if not Path(DB_PATH).exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch all active skills
    cursor.execute("SELECT skill_id, action_name, category, description FROM skill_registry;")
    skills = cursor.fetchall()

    mapped_count = 0
    assigned_permissions = 0

    for skill_id, action_name, category, description in skills:
        text_corpus = f"{action_name} {category} {description}".lower()
        matched_perms = set()

        for perm_id, keywords in HEURISTICS.items():
            if any(kw in text_corpus for kw in keywords):
                matched_perms.add(perm_id)

        # Baseline fallback: If no keyword matched, assign standard read access
        if not matched_perms:
            matched_perms.add("fs:read_file")

        # Insert skill permission mappings
        for perm_id in matched_perms:
            cursor.execute("""
                INSERT OR IGNORE INTO skill_permissions (skill_id, perm_id)
                VALUES (?, ?);
            """, (skill_id, perm_id))
            assigned_permissions += 1

        mapped_count += 1

    conn.commit()
    conn.close()

    print(f"Successfully processed {mapped_count} skills and seeded {assigned_permissions} permission bindings.")

if __name__ == "__main__":
    seed_skill_permissions()