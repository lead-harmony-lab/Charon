"""
charon/agents/overseer/constants.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Action mappings and valid action definitions for Overseer.
"""

VALID_OVERSEER_ACTIONS = (
    "optimize_databases",
    "audit_vector_store",
    "prune_logs_and_cache",
    "prune_orphaned_assets",
    "prune_stale_workspaces",
    "get_system_health",
    "audit_resource_guard",
    "resolve_skill_gaps",
    "run_full_maintenance",
)

ACTION_MAP = {
    # SQLite Database Optimization
    "optimize_databases": "optimize_databases",
    "optimize_db": "optimize_databases",
    "vacuum": "optimize_databases",
    "vacuum_db": "optimize_databases",
    "optimize": "optimize_databases",
    "compact_db": "optimize_databases",

    # Vector Store Auditing
    "audit_vector_store": "audit_vector_store",
    "audit_vector": "audit_vector_store",
    "vector_audit": "audit_vector_store",
    "audit_chroma": "audit_vector_store",
    "chroma_audit": "audit_vector_store",

    # Log and Cache Pruning
    "prune_logs_and_cache": "prune_logs_and_cache",
    "prune_logs": "prune_logs_and_cache",
    "prune_cache": "prune_logs_and_cache",
    "clean_logs": "prune_logs_and_cache",
    "clean_cache": "prune_logs_and_cache",

    # Workspace Pruning
    "prune_stale_workspaces": "prune_stale_workspaces",
    "prune_workspaces": "prune_stale_workspaces",
    "clean_workspaces": "prune_stale_workspaces",
    "prune_workspace": "prune_stale_workspaces",
    "clean_workspace": "prune_stale_workspaces",
    "sweep_workspaces": "prune_stale_workspaces",

    # Orphaned Asset Pruning
    "prune_orphaned_assets": "prune_orphaned_assets",
    "prune_assets": "prune_orphaned_assets",
    "clean_assets": "prune_orphaned_assets",
    "prune_orphans": "prune_orphaned_assets",
    "sweep_assets": "prune_orphaned_assets",

    # System Telemetry & Health
    "get_system_health": "get_system_health",
    "system_health": "get_system_health",
    "telemetry": "get_system_health",
    "health": "get_system_health",
    "health_check": "get_system_health",
    "status": "get_system_health",

    # Resource Guard Auditing
    "audit_resource_guard": "audit_resource_guard",
    "check_resources": "audit_resource_guard",
    "resource_guard": "audit_resource_guard",
    "enforce_resource_guard": "audit_resource_guard",
    "audit_resources": "audit_resource_guard",
    "resource_audit": "audit_resource_guard",
    "check_limits": "audit_resource_guard",

    # Skill Gap Resolution
    "resolve_skill_gaps": "resolve_skill_gaps",
    "fix_gaps": "resolve_skill_gaps",
    "resolve_gaps": "resolve_skill_gaps",

    # Full Maintenance Suite
    "run_full_maintenance": "run_full_maintenance",
    "full_maintenance": "run_full_maintenance",
    "maintenance": "run_full_maintenance",
    "clean_all": "run_full_maintenance",
    "full_clean": "run_full_maintenance",
}