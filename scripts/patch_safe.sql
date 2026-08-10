PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

--------------------------------------------------------------------------------
-- 1. Safely migrate skill_permissions data without loss
--------------------------------------------------------------------------------
-- Create temporary table with the new schema (perm_id FK removed)
CREATE TABLE skill_permissions_new (
  skill_id TEXT NOT NULL,
  perm_id TEXT NOT NULL,
  PRIMARY KEY(skill_id, perm_id),
  FOREIGN KEY(skill_id) REFERENCES skill_registry(skill_id) ON DELETE CASCADE
);

-- Copy all existing data across
INSERT INTO skill_permissions_new (skill_id, perm_id)
SELECT skill_id, perm_id FROM skill_permissions;

-- Drop old table and rename new table
DROP TABLE skill_permissions;
ALTER TABLE skill_permissions_new RENAME TO skill_permissions;

--------------------------------------------------------------------------------
-- 2. Re-create Triggers & Clean Up
--------------------------------------------------------------------------------
-- Re-create quarantine trigger
DROP TRIGGER IF EXISTS auto_quarantine_unknown_permission;

CREATE TRIGGER auto_quarantine_unknown_permission
AFTER INSERT ON skill_permissions
FOR EACH ROW
BEGIN
  UPDATE skill_registry
  SET
    status = 'QUARANTINED',
    quarantine_reason = 'UNKNOWN_PERMISSION_REQUESTED: ' || NEW.perm_id,
    updated_at = CURRENT_TIMESTAMP
  WHERE skill_id = NEW.skill_id
    AND NEW.perm_id NOT IN (SELECT perm_id FROM permission_registry);
END;

-- FIFO Pruning Triggers (Caps QUARANTINED rows at 20)
DROP TRIGGER IF EXISTS prune_quarantined_skills_on_update;
DROP TRIGGER IF EXISTS prune_quarantined_skills_on_insert;

CREATE TRIGGER prune_quarantined_skills_on_update
AFTER UPDATE OF status ON skill_registry
WHEN NEW.status = 'QUARANTINED'
BEGIN
  DELETE FROM skill_registry
  WHERE status = 'QUARANTINED'
    AND skill_id NOT IN (
      SELECT skill_id FROM skill_registry
      WHERE status = 'QUARANTINED'
      ORDER BY updated_at DESC, indexed_at DESC
      LIMIT 20
    );
END;

CREATE TRIGGER prune_quarantined_skills_on_insert
AFTER INSERT ON skill_registry
WHEN NEW.status = 'QUARANTINED'
BEGIN
  DELETE FROM skill_registry
  WHERE status = 'QUARANTINED'
    AND skill_id NOT IN (
      SELECT skill_id FROM skill_registry
      WHERE status = 'QUARANTINED'
      ORDER BY updated_at DESC, indexed_at DESC
      LIMIT 20
    );
END;

--------------------------------------------------------------------------------
-- 3. Additional Guardrails
--------------------------------------------------------------------------------
-- Drop redundant index
DROP INDEX IF EXISTS idx_agent_skill_map_agent;

-- Prevent inactive agent assignments on INSERT into system_roles
DROP TRIGGER IF EXISTS prevent_inactive_agent_role_assignment_insert;

CREATE TRIGGER prevent_inactive_agent_role_assignment_insert
BEFORE INSERT ON system_roles
WHEN NEW.agent_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT is_active FROM agent_registry WHERE agent_id = NEW.agent_id) = 0
    THEN RAISE(ABORT, 'Operation blocked: Cannot assign an inactive agent to a system role.')
  END;
END;

COMMIT;

PRAGMA foreign_keys = ON;