"""
charon/cli/ui.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Visual effects, spinner, and terminal rendering helpers for Charon CLI.
"""

import itertools
import sys
import threading
import time
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown

console = Console()


class CharonSpinner:
    """Thread-safe terminal spinner supporting dynamic status updates."""

    def __init__(self, message: str = "Tending to the arrangements..."):
        self.spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        self.message = message
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def spin(self) -> None:
        while self.running:
            with self._lock:
                msg = self.message
            # \r clears back to start, \033[K clears to end of line to eliminate artifact text
            sys.stdout.write(f"\r\033[K\033[36m{next(self.spinner)}\033[0m {msg}")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def start(self, message: Optional[str] = None) -> None:
        with self._lock:
            if message:
                self.message = message
            if not self.running:
                self.running = True
                self.thread = threading.Thread(target=self.spin, daemon=True)
                self.thread.start()

    def update(self, message: str) -> None:
        """Dynamically updates the spinner text without restarting the animation thread."""
        with self._lock:
            self.message = message

    def stop(self) -> None:
        with self._lock:
            if self.running:
                self.running = False
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=0.5)
                self.thread = None


def teletype_print(text: str, delay: float = 0.015) -> None:
    """Prints plain text character-by-character to simulate a concierge feed."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def render_response(message: str) -> None:
    """Renders formatted response content cleanly, preserving multiline command outputs."""
    if message.startswith("[System]: "):
        message = message[10:]

    if any(marker in message for marker in ["```", "### ", "## ", "# ", "* ", "- "]):
        console.print()
        console.print(Markdown(message))
    elif "\n" in message:
        console.print()
        console.print(message)
    else:
        teletype_print(message)
