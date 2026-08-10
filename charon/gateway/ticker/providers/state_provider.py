"""
charon/gateway/ticker/providers/state_provider.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Ticker provider adapter for SQLite StateManager items.
"""

import logging
from typing import List, Optional
from charon.core.state import StateManager
from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerProvider.StateManager")


class StateManagerTickerProvider(BaseTickerProvider):
    """Adapts StateManager active ticker db records into TickerSlide objects."""

    def __init__(self, state_manager: Optional[StateManager] = None) -> None:
        super().__init__(provider_id="state_manager", enabled=True)
        self.state_manager = state_manager

    async def get_slides(self) -> List[TickerSlide]:
        if not self.state_manager:
            return []

        try:
            items = await self.state_manager.get_active_ticker_items(limit=10)
            slides: List[TickerSlide] = []

            for item in items:
                # Support custom text fields or fallback formatted string
                text = item.get("display_text") or item.get("message") or str(item)
                priority = item.get("priority", 0)

                slides.append(
                    TickerSlide(
                        provider_id=self.provider_id,
                        display_text=text,
                        priority=priority,
                        data=item,
                    )
                )
            return slides
        except Exception as err:
            logger.warning(f"Failed to fetch StateManager ticker items: {err}")
            return []