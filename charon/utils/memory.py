"""
charon/utils/memory.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Charon Memory Utilities: Rolling Conversation Buffer for Prompt Context.
"""

import logging
from typing import Dict, List

logger = logging.getLogger("Charon.Utils.Memory")


class ConversationBuffer:
    """Rolling RAM memory buffer to maintain short-term context across D-Bus transmissions."""

    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []

    def add_user_message(self, text: str) -> None:
        """Appends a user prompt to context."""
        self.add_turn("user", text)

    def add_system_message(self, text: str) -> None:
        """Appends a Charon daemon response to context."""
        self.add_turn("assistant", text)

    def add_turn(self, role: str, content: str) -> None:
        """Appends a single turn and enforces max context length."""
        self.history.append({"role": role, "content": content})
        # Keep only the last (max_turns * 2) individual messages
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2) :]

    def get_context_string(self) -> str:
        """Formats buffered history into a plain text block for model system prompts."""
        if not self.history:
            return "No prior conversational context."

        formatted = []
        for msg in self.history:
            speaker = "User" if msg["role"].lower() in ["user", "human"] else "Charon"
            formatted.append(f"{speaker}: {msg['content']}")
        return "\n".join(formatted)

    def clear(self) -> None:
        """Flushes active context buffer (e.g., on topic change or exit)."""
        self.history.clear()
        logger.info("Conversation memory buffer cleared.")
