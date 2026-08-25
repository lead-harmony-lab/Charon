"""
charon/core/services/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Charon Core System & Domain Services Package.
Exposes core system lifecycle management, process monitoring, and external service utilities.
"""

from charon.core.services.systemd import (
    control_unit,
    get_monitored_units_status,
    get_registered_units,
    get_unit_file_content,
    inspect_unit,
    register_unit,
    unregister_unit,
    update_unit_file_content,
)

__all__ = [
    "get_registered_units",
    "register_unit",
    "unregister_unit",
    "inspect_unit",
    "get_monitored_units_status",
    "control_unit",
    "get_unit_file_content",
    "update_unit_file_content",
]