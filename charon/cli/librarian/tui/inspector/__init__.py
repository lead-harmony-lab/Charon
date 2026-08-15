"""
charon/cli/librarian/tui/inspector/__init__.py
System Version: v0.2.0 | File Revision: 3.3.0

Module: Inspector TUI package facade exporting main entry points for backward compatibility.
"""

from charon.cli.librarian.tui.inspector.card import inspect_skill_card, inspect_skill_list

__all__ = ["inspect_skill_list", "inspect_skill_card"]