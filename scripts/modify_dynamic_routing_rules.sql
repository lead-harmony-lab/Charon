DROP TABLE IF EXISTS dynamic_routing_rules;

CREATE TABLE dynamic_routing_rules (
    rule_id TEXT PRIMARY KEY,
    trigger TEXT UNIQUE NOT NULL,
    agent_id TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE CASCADE
);

CREATE INDEX idx_dynamic_rule_trigger ON dynamic_routing_rules(trigger);
CREATE INDEX idx_dynamic_rule_agent ON dynamic_routing_rules(agent_id);