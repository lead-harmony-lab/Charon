"""
charon/db/bootstrap.py
System Version: v0.2.1 | File Revision: 2.0.0

Bootstraps the agent_registry, system_roles, and route_registry schemas
and seeds initial immutable system slots using role-based abstraction.
"""

import logging
from pathlib import Path
from typing import List, Tuple

from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Bootstrap")

# Baseline Bootstrap Agent (Used if agent_registry is completely unpopulated)
CORE_BOOTSTRAP_AGENT_ID = "core_system_agent"

# Mandatory System Roles mapping (Role Name, Search Query / Description)
SYSTEM_ROLE_DEFINITIONS: List[Tuple[str, str, str]] = [
    (
        "default_system_generalist",
        "Generalist",
        "Primary conversational and general execution node.",
    ),
    (
        "default_system_planner",
        "Planner",
        "Primary orchestrator and step-by-step task planner.",
    ),
    (
        "default_system_engineer",
        "Engineer",
        "Diagnostic, repair, and skill-gap resolution agent.",
    ),
    (
        "system_fallback",
        "Generalist",
        "Universal fallback agent when role or route resolution fails.",
    ),
    (
        "system_archivist",
        "Archivist",
        "Core memory, relational storage, and RAG retrieval node.",
    ),
    (
        "system_steward",
        "Steward",
        "OS automation and external system command dispatch node.",
    ),
    (
        "role_quartermaster",
        "Quartermaster",
        "Inventory auditing and resource tracking node.",
    ),
    (
        "role_cleaner",
        "Cleaner",
        "Workspace hygiene and file maintenance node.",
    ),
    (
        "role_spark",
        "Spark",
        "Low-level firmware compilation and hardware build node.",
    ),
    (
        "role_machinist",
        "Machinist",
        "CAD processing and fabrication specification node.",
    ),
    (
        "role_scout",
        "Scout",
        "External web intelligence and scraping node.",
    ),
    (
        "role_overseer",
        "Overseer",
        "System telemetry and event auditing node.",
    ),
]

# Base 11 Seed Mappings (Action Trigger -> Target System Role)
INITIAL_SYSTEM_ROUTES: List[Tuple[str, str, str]] = [
    ("audit_inventory", "role_quartermaster", "Inventory auditing and tracking"),
    ("query_memory", "system_archivist", "Long-term vector and relational memory lookups"),
    ("manage_workspace", "role_cleaner", "Workspace hygiene and temp file cleanup"),
    ("compile_firmware", "role_spark", "Low-level code compilation and hardware build"),
    ("process_cad", "role_machinist", "CAD file conversion and machining specs"),
    ("analyze_roadmap", "default_system_planner", "Strategic project planning and task decomposition"),
    ("execute_diagnostic", "default_system_engineer", "System diagnostic execution and error tracing"),
    ("answer_query", "default_system_generalist", "General reasoning and conversational query handling"),
    ("web_search", "role_scout", "External web scraping and intelligence gathering"),
    ("audit_telemetry", "role_overseer", "Telemetry processing and event auditing"),
    ("transmit_command", "system_steward", "OS automation and external system command dispatch"),
]


def init_route_registry(db_path: Path) -> None:
    """Initializes system schemas and seeds immutable baseline system routes and roles."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 1. Ensure prerequisite tables exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_registry (
        agent_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        description TEXT NOT NULL,
        default_action TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        system_prompt TEXT DEFAULT ''
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_roles (
        role_name TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS route_registry (
        route_id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_trigger TEXT UNIQUE NOT NULL,
        target_role TEXT NOT NULL,
        fallback_role TEXT DEFAULT 'system_fallback',
        route_type TEXT CHECK(route_type IN ('SYSTEM', 'USER_OVERRIDE', 'DYNAMIC_AUTO', 'EPHEMERAL')) NOT NULL DEFAULT 'DYNAMIC_AUTO',
        is_active INTEGER NOT NULL DEFAULT 1,
        description TEXT,
        created_by TEXT DEFAULT 'system',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_count INTEGER DEFAULT 0,
        last_executed_at TIMESTAMP,
        FOREIGN KEY(target_role) REFERENCES system_roles(role_name) ON DELETE RESTRICT,
        FOREIGN KEY(fallback_role) REFERENCES system_roles(role_name) ON DELETE SET NULL
    );
    """)

    # 2. Prevent NOT NULL errors on empty DB: Guarantee baseline agent exists
    cursor.execute("""
    INSERT INTO agent_registry (agent_id, display_name, description, default_action, system_prompt)
    VALUES (?, 'System Core Assistant', 'Fallback execution node for system bootstrap.', 'answer_query', '')
    ON CONFLICT(agent_id) DO NOTHING;
    """, (CORE_BOOTSTRAP_AGENT_ID,))

    # 3. Seed/Update System Roles
    for role_name, match_pattern, desc in SYSTEM_ROLE_DEFINITIONS:
        cursor.execute("""
        INSERT INTO system_roles (role_name, agent_id, description)
        VALUES (
            ?,
            COALESCE(
                (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE ? OR display_name LIKE ?) AND is_active = 1 LIMIT 1),
                (SELECT agent_id FROM agent_registry WHERE is_active = 1 LIMIT 1),
                ?
            ),
            ?
        )
        ON CONFLICT(role_name) DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP,
            agent_id = COALESCE(
                (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE ? OR display_name LIKE ?) AND is_active = 1 LIMIT 1),
                system_roles.agent_id
            );
        """, (
            role_name, f"%{match_pattern}%", f"%{match_pattern}%", CORE_BOOTSTRAP_AGENT_ID, desc,
            f"%{match_pattern}%", f"%{match_pattern}%"
        ))

    # 4. Seed Base 11 Immutable System Routes
    for trigger, target_role, desc in INITIAL_SYSTEM_ROUTES:
        cursor.execute("""
        INSERT INTO route_registry (action_trigger, target_role, fallback_role, route_type, description, created_by)
        VALUES (?, ?, 'system_fallback', 'SYSTEM', ?, 'system_bootstrapper')
        ON CONFLICT(action_trigger) DO UPDATE SET
            target_role = EXCLUDED.target_role,
            fallback_role = EXCLUDED.fallback_role,
            description = EXCLUDED.description,
            route_type = 'SYSTEM';
        """, (trigger, target_role, desc))

    conn.commit()
    conn.close()
    logger.info("Database schema and system routes initialized/seeded successfully.")