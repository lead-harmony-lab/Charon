"""
charon/cli/librarian/db/__init__.py
System Version: v0.2.0 | File Revision: 2.2.1

Module: Public entry point for charon.cli.librarian.db sub-package.
"""

from .audit import cleanup_orphaned_agent_mappings_db, perform_state_audit
from .contracts import (
    bind_system_action_to_contract,
    get_available_system_contracts,
    get_system_action_contract,
    sync_system_actions,
)
from .gaps import (
    get_open_gaps,
    get_open_gaps_count,
    get_quarantined_orphans_count,
    get_resolved_gaps_count,
    purge_resolved_gaps_db,
    resolve_gap_db,
    vacuum_db,
)
from .permissions import (
    get_active_agent_ids,
    get_registered_agents,
    get_skill_defaults,
    get_skill_permissions,
    grant_agent_permission_db,
    resolve_skill_contract,
    revoke_agent_permission_db,
    set_agent_default_skill_db,
    update_agent_default_action,
)
from .skills import (
    get_deficient_skills_db,
    get_quarantined_skills_db,
    get_skill_by_id,
    get_skill_entry_and_status,
    get_skill_inventory_db,
    migrate_skill_id_in_db,
    purge_skill_records,
    register_and_bind_skill_db,
    register_skill_in_db,
    repair_quarantined_skill_db,
    unregister_skill_db,
)
from .sync import flag_quarantined_orphans, get_plugin_actions, run_sync
from .utils import _slugify, get_db_path

__all__ = [
    # Utilities & Core State
    "get_db_path",
    "_slugify",
    "perform_state_audit",
    "cleanup_orphaned_agent_mappings_db",
    # Skill Registry CRUD & Diagnostics
    "get_skill_by_id",
    "get_skill_inventory_db",
    "register_skill_in_db",
    "register_and_bind_skill_db",
    "unregister_skill_db",
    "migrate_skill_id_in_db",
    "get_skill_entry_and_status",
    "purge_skill_records",
    "get_deficient_skills_db",
    "get_quarantined_skills_db",
    "repair_quarantined_skill_db",
    # System Action Contracts
    "get_system_action_contract",
    "sync_system_actions",
    "get_available_system_contracts",
    "bind_system_action_to_contract",
    # Filesystem Sync & Plugin Inspection
    "get_plugin_actions",
    "flag_quarantined_orphans",
    "run_sync",
    # RBAC & Agent Permissions
    "get_active_agent_ids",
    "get_registered_agents",
    "resolve_skill_contract",
    "get_skill_permissions",
    "get_skill_defaults",
    "grant_agent_permission_db",
    "revoke_agent_permission_db",
    "set_agent_default_skill_db",
    "update_agent_default_action",
    # Skill Gap, Quarantine & Maintenance Operations
    "get_quarantined_orphans_count",
    "get_open_gaps_count",
    "get_resolved_gaps_count",
    "get_open_gaps",
    "resolve_gap_db",
    "purge_resolved_gaps_db",
    "vacuum_db",
]