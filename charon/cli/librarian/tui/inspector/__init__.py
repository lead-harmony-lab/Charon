"""Inspector TUI package facade exporting main entry points for backward compatibility."""

from charon.cli.librarian.tui.inspector.card import inspect_skill_card, inspect_skill_list

__all__ = ["inspect_skill_list", "inspect_skill_card"]