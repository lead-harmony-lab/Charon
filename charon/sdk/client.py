"""
charon/sdk/client.py
System Version: v0.1.0 | File Revision: 2.0.0

Main CharonClientNode assembly handling WebSocket networking and event loops.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union
import urllib.parse

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from charon.sdk.core_api import CoreApiMixin
from charon.sdk.models import API_KEY_HEADER_NAME, CHARON_API_KEY, EventHandler, WSEvent
from charon.sdk.router_api import RouterApiMixin
from charon.sdk.skills_api import SkillForgeApiMixin
from charon.sdk.telemetry import HardwareTelemetry

logger = logging.getLogger("CharonSDK")


class CharonClientNode(CoreApiMixin, RouterApiMixin, SkillForgeApiMixin):
    """Asynchronous client node SDK for Charon Engine daemon interactions.

    Handles persistent WebSocket connectivity, automatic exponential-backoff
    reconnections, targeted event routing via decorators, task dispatching,
    API key authorization, dynamic skill forging, router control management,
    and automatic hardware telemetry discovery.
    """

    def __init__(
        self,
        client_id: str,
        engine_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        default_context: Optional[Dict[str, Any]] = None,
        auto_reconnect: bool = True,
        auto_discover_hardware: bool = True,
    ):
        self.client_id = client_id
        self.engine_url = engine_url.rstrip("/")
        self.api_key = api_key or CHARON_API_KEY
        self.auto_reconnect = auto_reconnect
        self.auto_discover_hardware = auto_discover_hardware

        # Base context with optional telemetry
        self.default_context = default_context or {}
        self.telemetry: Dict[str, Any] = {}

        if self.auto_discover_hardware:
            self.refresh_telemetry()

        # Derive WebSocket URL with auth params
        parsed_url = urllib.parse.urlparse(self.engine_url)
        ws_scheme = "wss" if parsed_url.scheme == "https" else "ws"
        query_params = urllib.parse.urlencode({
            "client_id": self.client_id,
            "api_key": self.api_key,
        })
        self.ws_url = f"{ws_scheme}://{parsed_url.netloc}/v1/ws?{query_params}"

        # Event handlers registry: event_type -> List[EventHandler]
        self._handlers: Dict[str, List[EventHandler]] = {}

        # Connection state management
        self._ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._connected: bool = False

        # Shared HTTP client for REST endpoints
        self._http_client: Optional[httpx.AsyncClient] = None

    def refresh_telemetry(self) -> Dict[str, Any]:
        """Re-samples hardware architecture and updates internal telemetry payload."""
        self.telemetry = HardwareTelemetry.collect()
        self.default_context["telemetry"] = self.telemetry
        logger.debug(f"Hardware telemetry refreshed for node '{self.client_id}'")
        return self.telemetry

    @property
    def is_connected(self) -> bool:
        """Returns True if the WebSocket connection is actively established."""
        return self._connected

    # ==========================================================================
    # Event Router Decorator & Handler Registration
    # ==========================================================================

    def on(self, event_type: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register a callback function for a specific WSEvent type."""

        def decorator(func: EventHandler) -> EventHandler:
            self.register_handler(event_type, func)
            return func

        return decorator

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        """Registers a callback function for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(
            f"Registered handler for '{event_type}' on node '{self.client_id}'"
        )

    # ==========================================================================
    # Connection Lifecycle Management
    # ==========================================================================

    async def connect(self) -> None:
        """Initializes HTTP client and starts background WebSocket listener task."""
        if self._running:
            logger.warning(f"Node '{self.client_id}' is already running.")
            return

        self._running = True
        headers = {API_KEY_HEADER_NAME: self.api_key}
        self._http_client = httpx.AsyncClient(
            base_url=self.engine_url,
            headers=headers,
            timeout=15.0,
        )
        self._listener_task = asyncio.create_task(self._ws_loop())
        logger.info(
            f"Charon SDK initialized for node '{self.client_id}'. Connecting..."
        )

    async def disconnect(self) -> None:
        """Cleanly terminates WebSocket connection and HTTP client."""
        logger.info(f"Disconnecting node '{self.client_id}'...")
        self._running = False
        self._connected = False

        if self._ws_connection:
            await self._ws_connection.close()
            self._ws_connection = None

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info(f"Node '{self.client_id}' disconnected cleanly.")

    async def listen_forever(self) -> None:
        """Awaits background WebSocket listener process indefinitely."""
        if not self._listener_task:
            await self.connect()

        try:
            await self._listener_task
        except asyncio.CancelledError:
            pass

    # ==========================================================================
    # Internal WebSocket Processing & Reconnect Loop
    # ==========================================================================

    async def _ws_loop(self) -> None:
        """Background loop managing WS connection, heartbeats, and reconnects."""
        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            try:
                logger.info(f"Attempting WebSocket connection to {self.ws_url}")

                ws_headers = {
                    API_KEY_HEADER_NAME: self.api_key,
                    "x-api-key": self.api_key,
                }

                async with websockets.connect(
                    self.ws_url,
                    additional_headers=ws_headers,
                    ping_interval=10,
                    ping_timeout=10,
                ) as websocket:
                    self._ws_connection = websocket
                    self._connected = True
                    backoff = 1.0

                    logger.info(
                        f"WebSocket connected to Charon Engine as '{self.client_id}'"
                    )

                    while self._running:
                        message = await websocket.recv()
                        await self._dispatch_ws_message(message)

            except (ConnectionClosed, OSError, Exception) as e:
                self._connected = False
                self._ws_connection = None

                if not self._running:
                    break

                if not self.auto_reconnect:
                    logger.error(
                        f"WebSocket connection lost: {e}. Auto-reconnect disabled."
                    )
                    break

                logger.warning(
                    f"WebSocket connection dropped ({e}). Reconnecting in {backoff:.1f}s..."
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, max_backoff)

    async def _dispatch_ws_message(
        self, raw_message: Union[str, bytes]
    ) -> None:
        """Parses incoming WebSocket payload into WSEvent and triggers registered handlers."""
        try:
            payload = json.loads(raw_message)
            event = WSEvent(**payload)

            handlers = self._handlers.get(
                event.event_type, []
            ) + self._handlers.get("*", [])

            if not handlers:
                logger.debug(
                    f"No handlers registered for event type '{event.event_type}'"
                )
                return

            tasks = [
                asyncio.create_task(handler(event)) for handler in handlers
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(
                f"Error parsing or handling WebSocket event payload: {e}"
            )