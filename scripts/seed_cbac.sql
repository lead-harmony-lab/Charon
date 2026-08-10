-- ============================================================================
-- CHARON CBAC INITIAL SEED SCRIPT
-- ============================================================================

BEGIN TRANSACTION;

-- ----------------------------------------------------------------------------
-- 1. SEED PERMISSION PRIMITIVES
-- ----------------------------------------------------------------------------
INSERT OR IGNORE INTO permission_registry (perm_id, group_id, scope_pattern, description) VALUES
  ('fs:read_file',      'FS_READ',      '*', 'Read files from filesystem'),
  ('fs:write_file',     'FS_WRITE',     '*', 'Write or modify files on filesystem'),
  ('net:http_request',  'NET_OUTBOUND', '*', 'Make HTTP/HTTPS network requests'),
  ('sys:shell_exec',    'SYS_EXEC',     '*', 'Execute shell commands or scripts');

-- ----------------------------------------------------------------------------
-- 2. GRANT DEFAULT GROUPS TO ROLES
-- Give all existing roles FS_READ by default so basic file access works.
-- ----------------------------------------------------------------------------
INSERT OR IGNORE INTO role_permission_groups (role_name, group_id)
SELECT role_name, 'FS_READ' FROM system_roles;

-- Grant elevated permissions based on role names (matches common patterns)
INSERT OR IGNORE INTO role_permission_groups (role_name, group_id)
SELECT role_name, 'NET_OUTBOUND'
FROM system_roles
WHERE LOWER(role_name) LIKE '%research%'
   OR LOWER(role_name) LIKE '%web%'
   OR LOWER(role_name) LIKE '%fetch%';

INSERT OR IGNORE INTO role_permission_groups (role_name, group_id)
SELECT role_name, 'FS_WRITE'
FROM system_roles
WHERE LOWER(role_name) LIKE '%code%'
   OR LOWER(role_name) LIKE '%dev%'
   OR LOWER(role_name) LIKE '%writer%'
   OR LOWER(role_name) LIKE '%system%';

INSERT OR IGNORE INTO role_permission_groups (role_name, group_id)
SELECT role_name, 'SYS_EXEC'
FROM system_roles
WHERE LOWER(role_name) LIKE '%code%'
   OR LOWER(role_name) LIKE '%exec%'
   OR LOWER(role_name) LIKE '%system%'
   OR LOWER(role_name) LIKE '%admin%';

COMMIT;