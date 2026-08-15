"""
charon/cli/librarian/database.py
System Version: v0.4.7 | Refactored Package Facade

Re-exports public database API for backward compatibility.
Primary implementation now resides in charon.cli.librarian.db.
"""

from pprint import pprint

from charon.cli.librarian.db import (
    _slugify,
    bind_system_action_to_contract,
    flag_quarantined_orphans,
    get_available_system_contracts,
    get_db_path,
    get_plugin_actions,
    get_skill_by_id,
    get_skill_entry_and_status,
    get_system_action_contract,
    migrate_skill_id_in_db,
    perform_state_audit,
    purge_skill_records,
    register_skill_in_db,
    run_sync,
    sync_system_actions,
)

__all__ = [
    "get_db_path",
    "_slugify",
    "get_skill_by_id",
    "register_skill_in_db",
    "migrate_skill_id_in_db",
    "get_skill_entry_and_status",
    "purge_skill_records",
    "get_system_action_contract",
    "sync_system_actions",
    "get_available_system_contracts",
    "bind_system_action_to_contract",
    "get_plugin_actions",
    "flag_quarantined_orphans",
    "run_sync",
    "perform_state_audit",
]

if __name__ == "__main__":
    pprint(perform_state_audit())