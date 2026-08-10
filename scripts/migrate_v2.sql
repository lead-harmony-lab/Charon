-- ============================================================================
-- CHARON SCHEMA V2 MIGRATION SCRIPT (IDEMPOTENT & SAFE)
-- Preserves all existing data while upgrading state engine capabilities.
-- ============================================================================

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- Clean up temporary tables if script was previously interrupted
DROP TABLE IF EXISTS system_roles_new;
DROP TABLE IF EXISTS skill_registry_new;

-- ----------------------------------------------------------------------------
-- 1. UPGRADE `system_roles` (Make agent_id nullable & add mandatory flags)
-- ----------------------------------------------------------------------------
CREATE TABLE system_roles_new (
  role_name TEXT PRIMARY KEY,
  agent_id TEXT,                              -- Nullable now for agent swapping
  is_mandatory INTEGER NOT NULL DEFAULT 0,    -- Harness requirement flag
  is_system_core INTEGER NOT NULL DEFAULT 0,   -- Core vs custom role flag
  description TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
);

-- Copy existing data, defaulting new flags to 0
INSERT INTO system_roles_new (role_name, agent_id, is_mandatory, is_system_core, description, updated_at)
SELECT role_name, agent_id, 0, 0, description, updated_at
FROM system_roles;

DROP TABLE system_roles;
ALTER TABLE system_roles_new RENAME TO system_roles;

-- ----------------------------------------------------------------------------
-- 2. UPGRADE `skill_registry` (Transition is_active to status enum)
-- ----------------------------------------------------------------------------
CREATE TABLE skill_registry_new (
  skill_id TEXT PRIMARY KEY,
  action_name TEXT NOT NULL UNIQUE,
  version TEXT NOT NULL DEFAULT '1.0.0',
  category TEXT DEFAULT 'General',
  description TEXT NOT NULL DEFAULT '',
  parameters TEXT DEFAULT '{}',
  system_requirements TEXT NOT NULL DEFAULT '[]',
  consumed_artifacts TEXT NOT NULL DEFAULT '[]',
  produced_artifacts TEXT NOT NULL DEFAULT '[]',
  entry_file_path TEXT NOT NULL,
  handler_name TEXT NOT NULL,
  status TEXT CHECK(status IN ('ACTIVE', 'QUARANTINED', 'DISABLED', 'ARCHIVED')) NOT NULL DEFAULT 'QUARANTINED',
  quarantine_reason TEXT DEFAULT NULL,
  is_global INTEGER DEFAULT 0,
  indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Preserve data: map is_active = 1 to 'ACTIVE' and 0 to 'DISABLED'
INSERT INTO skill_registry_new (
  skill_id, action_name, version, category, description, parameters,
  system_requirements, consumed_artifacts, produced_artifacts, entry_file_path,
  handler_name, status, quarantine_reason, is_global, indexed_at, updated_at
)
SELECT
  skill_id, action_name, version, category, description, parameters,
  system_requirements, consumed_artifacts, produced_artifacts, entry_file_path,
  handler_name,
  CASE WHEN is_active = 1 THEN 'ACTIVE' ELSE 'DISABLED' END,
  NULL,
  is_global, indexed_at, updated_at
FROM skill_registry;

DROP TABLE skill_registry;
ALTER TABLE skill_registry_new RENAME TO skill_registry;

-- ----------------------------------------------------------------------------
-- 3. UPGRADE `idle_ticker_feed` (Add desktop interaction support)
-- ----------------------------------------------------------------------------
ALTER TABLE idle_ticker_feed ADD COLUMN urgency TEXT CHECK(urgency IN ('LOW', 'NORMAL', 'CRITICAL')) NOT NULL DEFAULT 'NORMAL';
ALTER TABLE idle_ticker_feed ADD COLUMN action_type TEXT DEFAULT NULL;
ALTER TABLE idle_ticker_feed ADD COLUMN action_payload TEXT DEFAULT '{}';

-- ----------------------------------------------------------------------------
-- 4. CREATE NEW CBAC & OVERSEER TABLES
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS permission_groups (
  group_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permission_registry (
  perm_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  scope_pattern TEXT NOT NULL DEFAULT '*',
  description TEXT NOT NULL,
  FOREIGN KEY (group_id) REFERENCES permission_groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS role_permission_groups (
  role_name TEXT NOT NULL,
  group_id TEXT NOT NULL,
  PRIMARY KEY (role_name, group_id),
  FOREIGN KEY (role_name) REFERENCES system_roles(role_name) ON DELETE CASCADE,
  FOREIGN KEY (group_id) REFERENCES permission_groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS skill_permissions (
  skill_id TEXT NOT NULL,
  perm_id TEXT NOT NULL,
  PRIMARY KEY (skill_id, perm_id),
  FOREIGN KEY (skill_id) REFERENCES skill_registry(skill_id) ON DELETE CASCADE,
  FOREIGN KEY (perm_id) REFERENCES permission_registry(perm_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS overseer_audit_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_type TEXT NOT NULL,
  target_entity TEXT NOT NULL,
  details TEXT DEFAULT '{}',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed Baseline Permission Groups
INSERT OR IGNORE INTO permission_groups (group_id, display_name, description) VALUES
  ('FS_READ', 'File System Read', 'Allows reading files from disk'),
  ('FS_WRITE', 'File System Write', 'Allows writing or modifying files on disk'),
  ('NET_OUTBOUND', 'Outbound Network', 'Allows HTTP and API requests to external networks'),
  ('SYS_EXEC', 'System Command Execution', 'Allows running shell processes and commands');

-- ----------------------------------------------------------------------------
-- 5. RE-CREATE INDEXES & TRIGGERS
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_agent_skill_map_agent ON agent_skill_map(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_skill_map_skill ON agent_skill_map(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_gaps_status ON skill_gaps(status);
CREATE INDEX IF NOT EXISTS idx_system_roles_agent ON system_roles(agent_id);
CREATE INDEX IF NOT EXISTS idx_route_trigger ON route_registry(action_trigger);
CREATE INDEX IF NOT EXISTS idx_route_type ON route_registry(route_type);
CREATE INDEX IF NOT EXISTS idx_route_active ON route_registry(is_active);
CREATE INDEX IF NOT EXISTS idx_task_status ON task_state(status);
CREATE INDEX IF NOT EXISTS idx_task_client ON task_state(client_id);
CREATE INDEX IF NOT EXISTS idx_ticker_active ON idle_ticker_feed(dismissed, expires_at);
CREATE INDEX IF NOT EXISTS idx_skill_status ON skill_registry(status);

-- Trigger: Prevent deactivating agents assigned to mandatory roles
DROP TRIGGER IF EXISTS prevent_mandatory_role_agent_deactivation;
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

-- Trigger: Prevent assigning inactive agents to roles
DROP TRIGGER IF EXISTS prevent_inactive_agent_role_assignment;
CREATE TRIGGER prevent_inactive_agent_role_assignment
BEFORE UPDATE OF agent_id ON system_roles
WHEN NEW.agent_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT is_active FROM agent_registry WHERE agent_id = NEW.agent_id) = 0
    THEN RAISE(ABORT, 'Operation blocked: Cannot assign an inactive agent to a system role.')
  END;
END;

-- Trigger: Auto-quarantine skills requesting unknown permissions
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

-- ----------------------------------------------------------------------------
-- 6. INTEGRITY VERIFICATION & COMMIT
-- ----------------------------------------------------------------------------
PRAGMA foreign_key_check;
COMMIT;
PRAGMA foreign_keys = ON;