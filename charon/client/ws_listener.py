"""
charon/client/ws_listener.py
System Version: v3.2.2 | File Revision: 3.2.2

Module: Asynchronous WebSocket client bridge running in a background thread.
Dispatches incoming stream events to GTK main loop safely via GLib.idle_add with API Key authentication.
Supports websockets v13+ (additional_headers) and legacy versions.
"""

import asyncio
import inspect
import json
import logging
import threading
from typing import Callable, Optional
import websockets
from gi.repository import GLib

logger = logging.getLogger("Charon.Client.WSListener")


class OverlayWSListener(threading.Thread):
    """Background listener thread consuming ws://localhost:8000/v1/concierge/stream."""

    def __init__(self, uri: str, api_key: Optional[str], on_event_callback: Callable[[dict], None]):
        super().__init__(daemon=True)
        self.uri = uri
        self.api_key = api_key
        self.on_event_callback = on_event_callback
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = True

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._listen_loop())

    async def _listen_loop(self):
        logger.info(f"[WSListener] Connecting to stream at: {self.uri}")

        # Determine header parameter name dynamically for websockets version compatibility
        connect_params = inspect.signature(websockets.connect).parameters
        header_kwarg = "additional_headers" if "additional_headers" in connect_params else "extra_headers"

        connect_kwargs = {}
        if self.api_key:
            connect_kwargs[header_kwarg] = {"X-API-Key": self.api_key}

        while self.running:
            try:
                async with websockets.connect(self.uri, **connect_kwargs) as ws:
                    logger.info("[WSListener] Stream connected successfully.")
                    while self.running:
                        raw_msg = await ws.recv()
                        try:
                            data = json.loads(raw_msg)
                            # Thread-safe dispatch to GTK main GUI loop
                            GLib.idle_add(self.on_event_callback, data)
                        except json.JSONDecodeError:
                            pass
            except Exception as err:
                logger.warning(f"[WSListener] Stream disconnected ({err}). Reconnecting in 3s...")
                await asyncio.sleep(3)