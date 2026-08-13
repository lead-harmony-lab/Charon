"""
charon/db/migrations/migrate_system_actions.py
System Version: v0.6.5 | File Revision: 1.0.0

Migration Script: System Actions Contract Table & Integrity Triggers.
Establishes the system_actions table to map abstract system action keys (e.g. 'sys_synthesis')
to dynamic skill action names while enforcing role-agent permission alignment via SQLite triggers.
"""

import logging
from pathlib import Path
import sqlite3
from typing import Optional, Union

from charon.config.paths import STATE_DB_PATH

logger = logging.getLogger("Charon.DB.Migrations.SystemActions")

MIGRATION_SQL = """
PRAGMA foreign_keys = ON;

-- =========================================================================
-- 1. Table Creation: system_actions
-- =========================================================================
CREATE TABLE IF NOT EXISTS "system_actions" (
  reserved_key TEXT PRIMARY KEY,
  action_name TEXT,
  required_role TEXT NOT NULL,
  is_mandatory INTEGER NOT NULL DEFAULT 1,
  description TEXT NOT NULL DEFAULT '',
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(action_name) REFERENCES skill_registry(action_name) ON UPDATE CASCADE ON DELETE RESTRICT,
  FOREIGN KEY(required_role) REFERENCES system_roles(role_name) ON DELETE RESTRICT
);

-- Indexes for resolution lookups
CREATE INDEX IF NOT EXISTS idx_system_actions_action ON system_actions(action_name);
CREATE INDEX IF NOT EXISTS idx_system_actions_role ON system_actions(required_role);

-- =========================================================================
-- 2. Trigger: Prevent unbinding mandatory system actions
-- =========================================================================
CREATE TRIGGER IF NOT EXISTS prevent_mandatory_action_unbinding
BEFORE UPDATE OF action_name ON system_actions
WHEN NEW.action_name IS NULL AND OLD.is_mandatory = 1
BEGIN
  SELECT RAISE(ABORT, 'Operation blocked: Mandatory system_action key cannot be unbound from a valid action_name.');
END;

-- =========================================================================
-- 3. Trigger: Enforce permission alignment on UPDATE
-- =========================================================================
CREATE TRIGGER IF NOT EXISTS enforce_system_action_permission_alignment_update
BEFORE UPDATE OF action_name ON system_actions
WHEN NEW.action_name IS NOT NULL
BEGIN
  SELECT CASE
    WHEN NOT EXISTS (
      SELECT 1 
      FROM system_roles sr
      JOIN agent_skill_map asm ON sr.agent_id = asm.agent_id
      JOIN skill_registry sk ON asm.skill_id = sk.skill_id
      WHERE sr.role_name = NEW.required_role
        AND sk.action_name = NEW.action_name
        AND sk.status = 'ACTIVE'
    )
    THEN RAISE(ABORT, 'Operation blocked: Target role agent does not possess an ACTIVE skill granting this action_name in agent_skill_map.')
  END;
END;

-- =========================================================================
-- 4. Trigger: Enforce permission alignment on INSERT
-- =========================================================================
CREATE TRIGGER IF NOT EXISTS enforce_system_action_permission_alignment_insert
BEFORE INSERT ON system_actions
WHEN NEW.action_name IS NOT NULL
BEGIN
  SELECT CASE
    WHEN NOT EXISTS (
      SELECT 1 
      FROM system_roles sr
      JOIN agent_skill_map asm ON sr.agent_id = asm.agent_id
      JOIN skill_registry sk ON asm.skill_id = sk.skill_id
      WHERE sr.role_name = NEW.required_role
        AND sk.action_name = NEW.action_name
        AND sk.status = 'ACTIVE'
    )
    THEN RAISE(ABORT, 'Operation blocked: Target role agent does not possess an ACTIVE skill granting this action_name in agent_skill_map.')
  END;
END;
"""


def seed_synthesis_contract(conn: sqlite3.Connection) -> None:
    """Seeds the initial 'sys_synthesis' contract bound to 'planner' role and dynamic action."""
    cursor = conn.cursor()

    # Verify 'planner' exists in system_roles
    cursor.execute("SELECT role_name FROM system_roles WHERE role_name = 'planner';")
    role_row = cursor.fetchone()
    if not role_row:
        logger.warning("[Migration] Role 'planner' not found in system_roles. Skipping initial seeding.")
        return

    # Check if 'execution_synthesize_synthesizer' exists and is ACTIVE
    cursor.execute(
        "SELECT action_name FROM skill_registry WHERE action_name = 'execution_synthesize_synthesizer' AND status = 'ACTIVE';"
    )
    skill_row = cursor.fetchone()
    action_target = skill_row[0] if skill_row else None

    try:
        cursor.execute(
            """
            INSERT INTO system_actions (reserved_key, action_name, required_role, is_mandatory, description)
            VALUES (?, ?, 'planner', 1, ?)
            ON CONFLICT(reserved_key) DO UPDATE SET
                action_name = excluded.action_name,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                "sys_synthesis",
                action_target,
                "Core capability for synthesizing execution outputs and context into blackboard payload responses.",
            ),
        )
        logger.info(f"[Migration] Successfully seeded 'sys_synthesis' bound to action '{action_target}'.")
    except sqlite3.Error as err:
        logger.error(f"[Migration] Failed to seed 'sys_synthesis' contract: {err}")
        raise


def run_migration(db_path: Optional[Union[Path, str]] = None) -> bool:
    """Applies the system_actions schema migration to the specified database."""
    target_path = Path(db_path) if db_path else STATE_DB_PATH
    if not target_path.exists():
        logger.error(f"[Migration] Database file does not exist at '{target_path}'.")
        return False

    logger.info(f"[Migration] Applying system_actions schema migration to: {target_path}")

    try:
        with sqlite3.connect(target_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()

            # Execute DDL
            cursor.executescript(MIGRATION_SQL)

            # Seed initial synthesis action contract
            seed_synthesis_contract(conn)

            conn.commit()
            logger.info("[Migration] Migration completed successfully.")
            return True

    except Exception as e:
        logger.critical(f"[Migration] System actions schema migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if not success:
        exit(1)