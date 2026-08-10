"""
charon/gateway/telemetry.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Overseer Telemetry & Modular Idle Ticker Reporter
Background loop sending system status updates, backend engine ping checks,
and dynamic ticker feeds via WebSockets.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional
import ollama

from charon.config import OLLAMA_HOST
from charon.core.state import StateManager
from charon.gateway.models import WSEvent
from charon.gateway.ticker.engine import ticker_engine, TickerEngine
from charon.gateway.ticker.providers.state_provider import StateManagerTickerProvider
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Telemetry")


class TelemetryReporter:
    """Monitors engine connectivity, system health telemetry, and broadcasts dynamic ticker feeds."""

    def __init__(
        self,
        queue_provider: Callable[[], int],
        gatekeeper_status_provider: Callable[[], bool],
        task_provider: Callable[[], Optional[str]],
        state_manager: Optional[StateManager] = None,
        engine: Optional[TickerEngine] = None,
    ) -> None:
        self.ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)
        self.get_queue_depth = queue_provider
        self.is_awaiting_gatekeeper = gatekeeper_status_provider
        self.get_current_task = task_provider
        self.state_manager = state_manager
        self.ticker_engine = engine or ticker_engine
        self.last_engine_state: Optional[bool] = None

        # Register default StateManager provider if state_manager exists
        if self.state_manager:
            self.ticker_engine.register_provider(
                StateManagerTickerProvider(self.state_manager)
            )

    async def verify_engine(self, retries: int = 3, delay: float = 2.0, timeout: float = 4.0) -> bool:
        """Ping Ollama host to confirm inference engine availability with explicit async timeout."""
        for attempt in range(1, retries + 1):
            try:
                await asyncio.wait_for(self.ollama_client.list(), timeout=timeout)
                return True
            except (asyncio.TimeoutError, Exception) as err:
                logger.debug(f"Engine health check attempt {attempt}/{retries} failed: {err}")
                if attempt < retries:
                    await asyncio.sleep(delay)
        return False

    def _safe_eval(self, provider: Callable[[], Any], fallback: Any) -> Any:
        """Helper to defensively execute telemetry metric providers without crashing the loop."""
        try:
            return provider()
        except Exception as e:
            provider_name = getattr(provider, "__name__", str(provider))
            logger.warning(f"Telemetry metric extraction failed for {provider_name}: {e}")
            return fallback

    async def start_loop(self, interval: float = 5.0) -> None:
        """Run overseer telemetry and idle ticker background reporting loop."""
        logger.info("Overseer telemetry and ticker loop initialized.")

        try:
            while True:
                try:
                    engine_online = await self.verify_engine(retries=1, delay=1.0, timeout=4.0)

                    # State transition alerts
                    if self.last_engine_state is not None:
                        if not engine_online and self.last_engine_state:
                            await manager.broadcast(
                                WSEvent(
                                    event_type="system_alert",
                                    agent_name="Overseer",
                                    task_id=None,
                                    data={
                                        "severity": "CRITICAL",
                                        "title": "Engine Disconnected",
                                        "message": f"Ollama backend ({OLLAMA_HOST}) unreachable!",
                                    },
                                )
                            )
                        elif engine_online and not self.last_engine_state:
                            await manager.broadcast(
                                WSEvent(
                                    event_type="system_alert",
                                    agent_name="Overseer",
                                    task_id=None,
                                    data={
                                        "severity": "INFO",
                                        "title": "Engine Restored",
                                        "message": "Ollama connection restored.",
                                    },
                                )
                            )

                    self.last_engine_state = engine_online

                    current_task = self._safe_eval(self.get_current_task, None)
                    queue_depth = self._safe_eval(self.get_queue_depth, 0)
                    gatekeeper_active = self._safe_eval(self.is_awaiting_gatekeeper, False)

                    is_idle = (current_task in (None, "Idle", "")) and queue_depth == 0

                    # Retrieve active slide safely
                    current_slide = None
                    try:
                        current_slide = await self.ticker_engine.get_active_slide()
                    except Exception as slide_err:
                        logger.debug(f"Failed to retrieve active ticker slide: {slide_err}")

                    slide_data = None
                    if current_slide:
                        if hasattr(current_slide, "model_dump"):
                            slide_data = current_slide.model_dump()
                        elif hasattr(current_slide, "dict"):
                            slide_data = current_slide.dict()
                        elif isinstance(current_slide, dict):
                            slide_data = current_slide

                    active_clients_count = 0
                    if hasattr(manager, "active_connections"):
                        try:
                            active_clients_count = len(manager.active_connections)
                        except Exception:
                            pass

                    telemetry_data = {
                        "status": "IDLE" if is_idle else "BUSY",
                        "engine_online": engine_online,
                        "queue_depth": queue_depth,
                        "active_clients": active_clients_count,
                        "awaiting_gatekeeper": gatekeeper_active,
                        "current_task": current_task or "Idle",
                        "current_slide": slide_data,
                    }

                    # 1. Primary Overseer Report
                    await manager.broadcast(
                        WSEvent(
                            event_type="overseer_report",
                            agent_name="Overseer",
                            task_id=current_task if isinstance(current_task, str) else None,
                            data=telemetry_data,
                        )
                    )

                    # 2. Dedicated Heartbeat Event for Top-Bar Extension Ticker
                    if is_idle:
                        await manager.broadcast(
                            WSEvent(
                                event_type="heartbeat_idle",
                                agent_name="Overseer",
                                task_id=None,
                                data={
                                    "status": "IDLE",
                                    "active_agent": None,
                                    "slide": slide_data,
                                    "default_text": "⚡ Charon: Ready",
                                },
                            )
                        )

                except Exception as e:
                    logger.error(f"Overseer reporter unexpected loop error: {e}", exc_info=True)

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Overseer telemetry loop cancelled.")