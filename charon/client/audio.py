"""
charon/client/audio.py
System Version: v3.9.0 | File Revision: 3.9.22

Module: Non-blocking, thread-safe sequential audio playback engine using PyAudio
and queue management to eliminate overlapping speech stream artifacts.
"""

import base64
import io
import logging
import queue
import threading
import wave

try:
    import pyaudio
except ImportError:
    pyaudio = None
    logging.warning("PyAudio is not installed. Speech playback will be disabled.")


class AudioPlayer:
    """Thread-safe sequential audio player for base64 WAV streams."""

    def __init__(self):
        self.pa = pyaudio.PyAudio() if pyaudio else None
        self.audio_queue = queue.Queue()
        self.is_playing = False

        # Dedicated worker thread to consume queue items sequentially
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

    def play_b64_wav(self, b64_data: str):
        """Enqueues base64 WAV audio for sequential playback."""
        if not self.pa or not b64_data:
            return
        self.audio_queue.put(b64_data)

    def clear_queue(self):
        """Flushes any pending audio chunks (e.g., when interrupted by user input)."""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break

    def _process_queue(self):
        while True:
            b64_data = self.audio_queue.get()
            self.is_playing = True
            try:
                self._play_chunk(b64_data)
            except Exception as e:
                logging.error(f"[AudioPlayer] Playback error: {e}")
            finally:
                self.is_playing = False
                self.audio_queue.task_done()

    def _play_chunk(self, b64_data: str):
        audio_bytes = base64.b64decode(b64_data)
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            stream = self.pa.open(
                format=self.pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
            )

            chunk_size = 1024
            data = wf.readframes(chunk_size)
            while data:
                stream.write(data)
                data = wf.readframes(chunk_size)

            stream.stop_stream()
            stream.close()