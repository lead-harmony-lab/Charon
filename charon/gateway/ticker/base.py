"""
charon/gateway/ticker/base.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Core data models and abstract base class for TickerEngine plugins.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TickerSlide(BaseModel):
    """Represents a single visual ticker slide frame broadcast to clients."""

    provider_id: str = Field(
        ...,
        description="Unique identifier of the originating provider (e.g. 'task_tracker')."
    )
    display_text: str = Field(
        ...,
        description="Formatted text rendered in the top bar (e.g. '📌 14:30: KiCad DRC Review')."
    )
    priority: int = Field(
        default=0,
        description="Priority level. 0 = Normal rotation. >0 = Priority takeover (e.g., pinned task)."
    )
    duration_seconds: int = Field(
        default=5,
        description="Suggested display duration in seconds."
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary provider context payload associated with the slide."
    )


class BaseTickerProvider(ABC):
    """Abstract Base Class for all dynamic ticker provider plugins."""

    def __init__(self, provider_id: str, enabled: bool = True) -> None:
        self.provider_id = provider_id
        self.enabled = enabled

    @abstractmethod
    async def get_slides(self) -> List[TickerSlide]:
        """
        Fetch active ticker slides from this provider.

        Returns an empty list if the provider has no active information to display.
        """
        pass