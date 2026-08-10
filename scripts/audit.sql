-- scripts/audit.sql
-- Charon System Role & Database Integrity Audit

.headers on
.mode column

.print ""
.print "======================================================="
.print " 1. SYSTEM ROLES & BACKING AGENT BINDINGS"
.print "======================================================="

SELECT
    sr.role_name,
    sr.agent_id,
    ar.display_name,
    COALESCE(ar.is_active, 0) AS agent_active,
    sr.description
FROM system_roles sr
LEFT JOIN agent_registry ar ON sr.agent_id = ar.agent_id;


.print ""
.print "======================================================="
.print " 2. ACTIVE REGISTERED AGENTS"
.print "======================================================="

SELECT
    agent_id,
    display_name,
    default_action,
    priority_weight,
    is_active
FROM agent_registry;


.print ""
.print "======================================================="
.print " 3. ROUTE REGISTRY & ROLE RESOLUTION"
.print "======================================================="

SELECT
    rr.route_id,
    rr.action_trigger,
    rr.target_role,
    sr.agent_id AS assigned_agent,
    rr.route_type,
    rr.is_active
FROM route_registry rr
LEFT JOIN system_roles sr ON rr.target_role = sr.role_name;


.print ""
.print "======================================================="
.print " 4. SKILL / ACTION TO AGENT MAPPINGS"
.print "======================================================="

SELECT
    asm.action_name,
    asm.agent_id,
    COALESCE(sr.is_active, 0) AS skill_active,
    COALESCE(sr.category, 'UNCATEGORIZED') AS category
FROM agent_skill_map asm
LEFT JOIN skill_registry sr ON asm.action_name = sr.action_name;


.print ""
.print "======================================================="
.print " 5. LOGGED SKILL / CAPABILITY GAPS"
.print "======================================================="

SELECT
    gap_id,
    action_name,
    requesting_agent,
    status,
    created_at
FROM skill_gaps;


.print ""
.print "======================================================="
.print " 6. INTEGRITY CHECKS & FAULT DIAGNOSTICS"
.print "======================================================="

WITH fault_diagnostics AS (
    -- 1. Broken Roles: Roles mapped to non-existent or inactive agents
    SELECT
        'BROKEN_ROLE' AS issue_type,
        sr.role_name AS context,
        'Points to missing or inactive agent_id: ' || COALESCE(sr.agent_id, 'NULL') AS detail
    FROM system_roles sr
    LEFT JOIN agent_registry ar ON sr.agent_id = ar.agent_id
    WHERE ar.agent_id IS NULL OR ar.is_active = 0

    UNION ALL

    -- 2. Broken Routes: Route action_trigger pointing to missing system role
    SELECT
        'INVALID_ROUTE_TARGET' AS issue_type,
        rr.action_trigger AS context,
        'Target role missing in system_roles: ' || COALESCE(rr.target_role, 'NULL') AS detail
    FROM route_registry rr
    LEFT JOIN system_roles sr ON rr.target_role = sr.role_name
    WHERE sr.role_name IS NULL

    UNION ALL

    -- 3. Broken Skill Maps: Mapped agent_id does not exist in agent_registry
    SELECT
        'UNMAPPED_SKILL_AGENT' AS issue_type,
        asm.action_name AS context,
        'Mapped to non-existent agent_id: ' || COALESCE(asm.agent_id, 'NULL') AS detail
    FROM agent_skill_map asm
    LEFT JOIN agent_registry ar ON asm.agent_id = ar.agent_id
    WHERE ar.agent_id IS NULL

    UNION ALL

    -- 4. Missing Critical Fallback Roles
    SELECT
        'MISSING_CRITICAL_ROLE' AS issue_type,
        'default_system_engineer' AS context,
        'Critical engineer fallback role is missing from system_roles table' AS detail
    WHERE NOT EXISTS (SELECT 1 FROM system_roles WHERE role_name = 'default_system_engineer')

    UNION ALL

    SELECT
        'MISSING_CRITICAL_ROLE' AS issue_type,
        'system_fallback' AS context,
        'Critical safety net fallback role is missing from system_roles table' AS detail
    WHERE NOT EXISTS (SELECT 1 FROM system_roles WHERE role_name = 'system_fallback')
)
SELECT * FROM fault_diagnostics
UNION ALL
SELECT
    'PASS' AS issue_type,
    'SYSTEM_OK' AS context,
    'No integrity faults or broken role bindings detected.' AS detail
WHERE NOT EXISTS (SELECT 1 FROM fault_diagnostics);