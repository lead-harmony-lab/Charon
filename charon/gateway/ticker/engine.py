"""
charon/gateway/ticker/engine.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: TickerEngine manager for dynamic slide collection, prioritization, and rotation.
"""

import logging
from typing import Dict, List, Optional
from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerEngine")


class TickerEngine:
    """Manages ticker provider plugins, handles round-robin rotation, and priority hijacking."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseTickerProvider] = {}
        self._rotation_index: int = 0

    def register_provider(self, provider: BaseTickerProvider) -> None:
        """Register a new ticker provider plugin."""
        self._providers[provider.provider_id] = provider
        logger.info(f"Registered TickerProvider: '{provider.provider_id}'")

    def unregister_provider(self, provider_id: str) -> None:
        """Unregister a provider plugin by ID."""
        if provider_id in self._providers:
            del self._providers[provider_id]
            logger.info(f"Unregistered TickerProvider: '{provider_id}'")

    async def get_active_slide(self) -> Optional[TickerSlide]:
        """
        Collects active slides from all enabled providers.

        Behavior:
        1. If any slide has priority > 0, returns the highest-priority slide immediately.
        2. Otherwise, cycles round-robin through normal slides across calls.
        """
        enabled_providers = [p for p in self._providers.values() if p.enabled]
        if not enabled_providers:
            return None

        all_slides: List[TickerSlide] = []

        for provider in enabled_providers:
            try:
                slides = await provider.get_slides()
                if slides:
                    all_slides.extend(slides)
            except Exception as e:
                logger.warning(
                    f"Ticker provider '{provider.provider_id}' failed during slide collection: {e}"
                )

        if not all_slides:
            return None

        # Check for high-priority slides (e.g., pinned tasks, critical alerts)
        priority_slides = [s for s in all_slides if s.priority > 0]
        if priority_slides:
            priority_slides.sort(key=lambda s: s.priority, reverse=True)
            return priority_slides[0]

        # Round-robin rotation for standard (priority == 0) slides
        self._rotation_index %= len(all_slides)
        selected_slide = all_slides[self._rotation_index]
        self._rotation_index = (self._rotation_index + 1) % len(all_slides)

        return selected_slide


# Global TickerEngine singleton instance
ticker_engine = TickerEngine()