#!/usr/bin/env python3
"""
Migration Script: Add 'domain' and 'skill_type' columns to skill_registry.
Reads directly from manifest.json associated with entry_file_path, falling back to 'category'.

Usage:
    python scripts/migrations/migrate_skill_schema_v2.py          # Dry run
    python scripts/migrations/migrate_skill_schema_v2.py --live   # Apply live modifications
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

try:
    from charon.config.paths import STATE_DB_PATH
except ImportError:
    STATE_DB_PATH = Path.home() / ".local" / "share" / "charon" / "charon_state.db"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migration")


def resolve_manifest_metadata(entry_file_path: str, fallback_category: str) -> tuple[str, str]:
    """Resolves domain and skill_type from manifest.json on disk, falling back to legacy category string."""
    domain, skill_type = None, None

    # 1. Inspect on-disk manifest.json via entry_file_path
    if entry_file_path:
        entry_path = Path(entry_file_path)
        manifest_path = entry_path.parent / "manifest.json"
        if not manifest_path.exists():
            manifest_path = entry_path.parent.parent / "manifest.json"

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    domain = data.get("domain")
                    skill_type = data.get("skill_type")
            except Exception as e:
                logger.debug(f"Could not parse manifest at {manifest_path}: {e}")

    # 2. Fallback to parsing legacy category string
    if not domain or not skill_type:
        cat_domain, cat_type = "General", "tool"
        if fallback_category:
            if " / " in fallback_category:
                parts = fallback_category.split(" / ", 1)
                cat_domain = parts[0].strip() or "General"
                raw_type = parts[1].strip().lower().replace(" ", "_")
                cat_type = raw_type if raw_type in ("tool", "contract") else "tool"
            else:
                cat_domain = fallback_category.strip()

        domain = domain or cat_domain
        skill_type = skill_type or cat_type

    return domain, skill_type


def run_migration(db_path: Path, live: bool = False) -> None:
    if not db_path.exists():
        logger.error(f"Database file not found at: {db_path}")
        sys.exit(1)

    print(f"Target Database : {db_path}")
    print(f"Execution Mode  : {'[LIVE] Modifying Database' if live else '[DRY-RUN] Previewing Changes Only'}")
    print("-" * 65)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(skill_registry)")
        columns = {row[1] for row in cursor.fetchall()}

        has_domain = "domain" in columns
        has_skill_type = "skill_type" in columns
        has_category = "category" in columns

        sql_ddl_statements = []
        if not has_domain:
            sql_ddl_statements.append("ALTER TABLE skill_registry ADD COLUMN domain TEXT DEFAULT 'General';")
        if not has_skill_type:
            sql_ddl_statements.append("ALTER TABLE skill_registry ADD COLUMN skill_type TEXT DEFAULT 'tool';")

        cat_clause = "category" if has_category else "'General'"
        cursor.execute(f"SELECT skill_id, action_name, entry_file_path, {cat_clause} FROM skill_registry")
        rows = cursor.fetchall()

        updates = []
        print(f"Found {len(rows)} skill record(s) to process:\n")
        for skill_id, action_name, entry_path, cat in rows:
            domain, skill_type = resolve_manifest_metadata(entry_path, cat)
            updates.append((domain, skill_type, skill_id))
            print(f"  • Skill ID         : {skill_id}")
            print(f"    Action           : {action_name}")
            print(f"    Mapped Domain    : {domain!r}")
            print(f"    Mapped Skill Type: {skill_type!r}\n")

        if not live:
            print("=" * 65)
            print("PROPOSED SQL ACTIONS (DRY-RUN):")
            if sql_ddl_statements:
                for stmt in sql_ddl_statements:
                    print(f"  {stmt}")
            else:
                print("  [Schema Notice] Columns 'domain' and 'skill_type' already exist.")

            print(f"  UPDATE skill_registry SET domain = ?, skill_type = ? WHERE skill_id = ?; ({len(updates)} row updates)")
            print("=" * 65)
            print("⚠️  DRY RUN COMPLETE: No modifications were committed to disk.")
            print("    To apply these changes live, execute with the '--live' flag:")
            print("    python scripts/migrations/migrate_skill_schema_v2.py --live")
        else:
            print("=" * 65)
            print("APPLYING LIVE MIGRATION...")
            for stmt in sql_ddl_statements:
                logger.info(f"Executing: {stmt}")
                cursor.execute(stmt)

            update_sql = "UPDATE skill_registry SET domain = ?, skill_type = ? WHERE skill_id = ?"
            cursor.executemany(update_sql, updates)

            conn.commit()
            print("✅ Migration completed successfully and changes committed!")
            print("=" * 65)

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed! Transaction aborted and rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate skill_registry to support 'domain' and 'skill_type'.")
    parser.add_argument("--db-path", type=Path, default=STATE_DB_PATH, help="Path to state SQLite database.")
    parser.add_argument("--live", action="store_true", help="Execute actual schema and record updates.")
    args = parser.parse_args()

    run_migration(args.db_path, live=args.live)