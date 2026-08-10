.headers on
.mode column

SELECT '=======================================================' AS '';
SELECT ' EXPANDED FAULT DIAGNOSTICS & SKILL AUDIT' AS '';
SELECT '=======================================================' AS '';

-- 1. Skills marked inactive but mapped to active agents
SELECT
    'INACTIVE_SKILL_MAPPED' AS issue_type,
    asm.agent_id AS context,
    'Agent mapped to inactive action: ' || asm.action_name AS detail
FROM agent_skill_map asm
JOIN skill_registry sr ON asm.action_name = sr.action_name
JOIN agent_registry ar ON asm.agent_id = ar.agent_id
WHERE sr.is_active = 0 AND ar.is_active = 1

UNION ALL

-- 2. Unlinked entries in agent_equipped_skills
SELECT
    'ORPHANED_EQUIPPED_SKILL' AS issue_type,
    aes.agent_id AS context,
    'skill_id not found in skill_registry: ' || aes.skill_id AS detail
FROM agent_equipped_skills aes
LEFT JOIN skill_registry sr ON aes.skill_id = sr.skill_id
WHERE sr.skill_id IS NULL

UNION ALL

-- 3. Failed or stuck tasks in task_state
SELECT
    'FAILED_TASK' AS issue_type,
    task_id AS context,
    'Status: ' || status || ' | Error: ' || COALESCE(error_message, 'None') AS detail
FROM task_state
WHERE status IN ('ERROR', 'FAILED', 'BLOCKED');