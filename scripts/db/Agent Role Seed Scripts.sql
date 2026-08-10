BEGIN TRANSACTION;

-- Ensure required system roles are mapped dynamically to available agents in agent_registry
INSERT INTO system_roles (role_name, agent_id, description)
VALUES
(
  'default_system_generalist',
  (SELECT agent_id FROM agent_registry WHERE is_active = 1 LIMIT 1),
  'Primary conversational and general execution node.'
),
(
  'default_system_planner',
  (SELECT agent_id FROM agent_registry WHERE is_active = 1 LIMIT 1),
  'Primary orchestrator and step-by-step task planner.'
),
(
  'default_system_engineer',
  (SELECT agent_id FROM agent_registry WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1),
  'Diagnostic, repair, and skill-gap resolution agent.'
),
(
  'system_fallback',
  (SELECT agent_id FROM agent_registry WHERE is_active = 1 LIMIT 1),
  'Universal fallback agent when role or route resolution fails.'
),
(
  'system_archivist',
  (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE '%Archivist%' OR display_name LIKE '%Archivist%') AND is_active = 1 LIMIT 1),
  'Core memory, relational storage, and RAG retrieval node.'
),
(
  'system_steward',
  (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE '%Steward%' OR display_name LIKE '%Steward%') AND is_active = 1 LIMIT 1),
  'OS automation and external system command dispatch node.'
)
ON CONFLICT(role_name) DO UPDATE SET
  updated_at = CURRENT_TIMESTAMP,
  -- Safely update the agent_id if the EXCLUDED row found a valid agent, otherwise keep the current one
  agent_id = COALESCE(EXCLUDED.agent_id, system_roles.agent_id);

COMMIT;