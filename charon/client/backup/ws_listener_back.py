"""
charon/client/ws_listener.py
System Version: v3.3.1 | File Revision: 3.3.1

Module: Asynchronous WebSocket client bridge running in a background thread.
Dispatches incoming stream events and connection state lifecycle events to GTK main loop.
Includes threaded SpeechStreamPlayer for synchronized audio and Cairo viseme animations.
"""

import asyncio
import base64
import inspect
import json
import logging
import threading
import time
from typing import Callable, Optional

import websockets
from gi.repository import GLib

try:
    import pyaudio
except ImportError:
    pyaudio = None
    logging.warning("PyAudio is not installed. Speech playback will be disabled.")

logger = logging.getLogger("Charon.Client.WSListener")


class SpeechStreamPlayer:
    def __init__(self, visualizer):
        self.visualizer = visualizer
        self.pyaudio_instance = pyaudio.PyAudio() if pyaudio else None
        self.stream = None
        self._playback_queue = []
        self._is_playing = False

    def play_chunk(self, audio_b64: str, sample_rate: int, visemes: list):
        """Decodes raw PCM data and launches thread for synced playback and viseme modulation."""
        if not self.pyaudio_instance:
            logger.error("[SpeechStreamPlayer] PyAudio unavailable, skipping playback.")
            return

        raw_audio = base64.b64decode(audio_b64)

        playback_thread = threading.Thread(
            target=self._run_synced_playback,
            args=(raw_audio, sample_rate, visemes),
            daemon=True
        )
        playback_thread.start()

    def _run_synced_playback(self, raw_audio: bytes, sample_rate: int, visemes: list):
        # Open PCM 16-bit Mono stream
        stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True
        )

        start_time = time.time()

        # 1. Schedule viseme mouth/aperture modulation
        def animate_visemes():
            elapsed_ms = (time.time() - start_time) * 1000.0

            # Find current frame in timeline
            active_viseme = next(
                (v for v in reversed(visemes) if v["offset_ms"] <= elapsed_ms),
                None
            )

            if active_viseme:
                # Drive the Cairo visualizer aperture opening directly
                aperture_opening = active_viseme.get("aperture_scale", 0.0)
                self.visualizer.set_speech_viseme(aperture_opening)

            if elapsed_ms < (visemes[-1]["offset_ms"] if visemes else 0):
                return GLib.SOURCE_CONTINUE

            # Reset aperture when done
            self.visualizer.set_speech_viseme(0.0)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(animate_visemes)

        # 2. Write PCM audio to speaker buffer
        stream.write(raw_audio)
        stream.stop_stream()
        stream.close()


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

        connect_params = inspect.signature(websockets.connect).parameters
        header_kwarg = "additional_headers" if "additional_headers" in connect_params else "extra_headers"

        connect_kwargs = {}
        if self.api_key:
            connect_kwargs[header_kwarg] = {"X-API-Key": self.api_key}

        while self.running:
            try:
                async with websockets.connect(self.uri, **connect_kwargs) as ws:
                    logger.info("[WSListener] Stream connected successfully.")

                    # Dispatch connection status event to GTK main loop
                    GLib.idle_add(self.on_event_callback, {
                        "event_type": "system",
                        "payload": {
                            "text": "Data link established",
                            "category": "thought",
                            "state": "observing"
                        }
                    })

                    while self.running:
                        raw_msg = await ws.recv()
                        try:
                            data = json.loads(raw_msg)
                            GLib.idle_add(self.on_event_callback, data)
                        except json.JSONDecodeError:
                            pass
            except Exception as err:
                logger.warning(f"[WSListener] Stream disconnected ({err}). Reconnecting in 3s...")
                GLib.idle_add(self.on_event_callback, {
                    "event_type": "system",
                    "payload": {
                        "text": "Data link lost",
                        "category": "warning",
                        "state": "alert"
                    }
                })
                await asyncio.sleep(3)