"""
scripts/db/seed_cbac.py
System Version: v0.2.1

Module: Seeding utility targeting the central Charon state database (~/.local/share/charon/charon_state.db).
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

# Target active Charon system database path
DEFAULT_DB_PATH = Path.home() / ".local/share/charon/charon_state.db"

INIT_PEC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contract_policies (
    contract_id TEXT PRIMARY KEY,
    contract_name TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    scope_limits TEXT NOT NULL DEFAULT '{}',
    rate_limit_rpm INTEGER DEFAULT NULL,
    token_boundary INTEGER DEFAULT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contract_policies_lookup
ON contract_policies(agent_id, skill_id);

CREATE INDEX IF NOT EXISTS idx_contract_policies_active
ON contract_policies(is_active);
"""

BASELINE_POLICIES: List[Dict[str, Any]] = [
    {
        "contract_id": "contract-system-engineer-v1",
        "contract_name": "System Engineer Policy Execution Container",
        "agent_id": "agent-engineer",
        "skill_id": "core.system.engineer",
        "scope_limits": {
            "allowed_actions": [
                "run_script_in_subprocess",
                "audit_written_artifacts",
                "apply_diff",
                "inspect_workspace",
                "git_commit",
            ],
            "allowed_paths": [
                "projects/*",
                "charon/core/skills/storage/dynamic/*",
                "tmp/sandbox/*",
            ],
            "max_file_size_mb": 25.0,
            "network_egress": True,
        },
        "rate_limit_rpm": 60,
        "token_boundary": 128000,
        "is_active": 1,
    },
    {
        "contract_id": "contract-librarian-v1",
        "contract_name": "Librarian Registry Governance Policy Execution Container",
        "agent_id": "agent-librarian",
        "skill_id": "core.system.librarian",
        "scope_limits": {
            "allowed_actions": [
                "index_skills",
                "validate_schema",
                "quarantine_package",
                "purge_resolved_gaps",
                "sync_db",
            ],
            "allowed_paths": [
                "charon/contracts/*",
                "charon/skills/*",
                "charon/db/*",
            ],
            "max_file_size_mb": 10.0,
            "network_egress": False,
        },
        "rate_limit_rpm": 120,
        "token_boundary": 64000,
        "is_active": 1,
    },
    {
        "contract_id": "contract-fallback-readonly-v1",
        "contract_name": "Global Default Read-Only PEC Policy",
        "agent_id": "*",
        "skill_id": "*",
        "scope_limits": {
            "allowed_actions": ["inspect_workspace", "audit_written_artifacts"],
            "allowed_paths": ["*"],
            "max_file_size_mb": 5.0,
            "network_egress": False,
        },
        "rate_limit_rpm": 30,
        "token_boundary": 32000,
        "is_active": 1,
    },
]


def seed_contract_policies(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Ensures contract_policies schema exists and seeds baseline PEC policies into SQLite."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Initialize schema
    cursor.executescript(INIT_PEC_SCHEMA_SQL)

    # 2. Upsert PEC policies
    upsert_query = """
    INSERT INTO contract_policies (
        contract_id,
        contract_name,
        agent_id,
        skill_id,
        scope_limits,
        rate_limit_rpm,
        token_boundary,
        is_active
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(contract_id) DO UPDATE SET
        contract_name = EXCLUDED.contract_name,
        agent_id = EXCLUDED.agent_id,
        skill_id = EXCLUDED.skill_id,
        scope_limits = EXCLUDED.scope_limits,
        rate_limit_rpm = EXCLUDED.rate_limit_rpm,
        token_boundary = EXCLUDED.token_boundary,
        is_active = EXCLUDED.is_active,
        updated_at = CURRENT_TIMESTAMP;
    """

    for policy in BASELINE_POLICIES:
        cursor.execute(
            upsert_query,
            (
                policy["contract_id"],
                policy["contract_name"],
                policy["agent_id"],
                policy["skill_id"],
                json.dumps(policy["scope_limits"]),
                policy["rate_limit_rpm"],
                policy["token_boundary"],
                policy["is_active"],
            ),
        )

    conn.commit()
    conn.close()
    print(f"Successfully initialized and seeded PEC policies in: {db_path}")


if __name__ == "__main__":
    seed_contract_policies()