"""
charon/exceptions.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Centralized exception definitions for Charon daemon and specialist agent handoffs.
"""

from typing import Any, Optional


class CharonBaseException(Exception):
    """Base exception class for all Charon system exceptions."""
    pass


class HandoffException(CharonBaseException):
    """Raised when an agent detects a request outside its domain or capabilities,

    triggering a dynamic inter-agent handoff inside the dispatcher.
    """

    def __init__(
        self,
        target_agent: str,
        reason: str,
        payload: Optional[Any] = None,
    ):
        self.target_agent = target_agent
        self.reason = reason
        self.payload = payload
        super().__init__(f"Dynamic handoff to {target_agent}: {reason}")