"""
charon/skill_forge_cli.py
System Version: v0.1.0 | File Revision: 3.0.0

Backwards-compatibility shim re-exporting Charon Skill Forge CLI functionality
from its consolidated home at `charon.cli.librarian.forge`.
"""

import sys
from charon.cli.librarian.forge import (
    build_parser,
    fetch_open_gaps,
    forge_skill_scaffold,
    main,
    promote_and_resolve_gap,
    register_disk_skills,
    sync_db,
)

__all__ = [
    "fetch_open_gaps",
    "forge_skill_scaffold",
    "register_disk_skills",
    "sync_db",
    "promote_and_resolve_gap",
    "build_parser",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())