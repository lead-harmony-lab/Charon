"""
charon/concierge/speech.py
System Version: v3.2.0 | File Revision: 3.2.1

Module: Speech Synthesis (TTS), Viseme Generator, and Audio Transcription (STT) Engine.
Provides voice generation with timed mouth-shape (viseme) cues for avatar HUD lip-syncing,
and transcribes inbound user microphone streams.
"""

import base64
import logging
import math
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Charon.Concierge.Speech")

# Standard Viseme Dictionary mapped to fundamental phonetic mouth shapes
VISEME_MAP = {
    "A": "viseme_aa",  # Open mouth (e.g. 'father')
    "E": "viseme_E",  # Mid open (e.g. 'bed')
    "I": "viseme_ih",  # Narrow wide (e.g. 'see')
    "O": "viseme_oh",  # Rounded open (e.g. 'go')
    "U": "viseme_ou",  # Rounded narrow (e.g. 'too')
    "B": "viseme_PP",  # Closed lips (P, B, M)
    "P": "viseme_PP",
    "M": "viseme_PP",
    "F": "viseme_FF",  # Lip bottom to teeth (F, V)
    "V": "viseme_FF",
    "S": "viseme_SS",  # Teeth closed (S, Z, C)
    "Z": "viseme_SS",
    "T": "viseme_DD",  # Tongue behind teeth (T, D, N)
    "D": "viseme_DD",
    "N": "viseme_DD",
    "SIL": "viseme_sil"  # Silence / Neutral
}


class SpeechEngine:
    """Handles TTS generation, viseme cue sequence calculation, and STT transcription."""

    def __init__(self, default_voice: str = "en_US-charon-neural", sample_rate: int = 22050):
        self.default_voice = default_voice
        self.sample_rate = sample_rate
        self.enabled = True
        logger.info(f"[SpeechEngine] Initialized with voice: {self.default_voice}")

    def generate_viseme_timeline(self, text: str, estimated_duration_sec: float) -> List[Dict[str, Any]]:
        """
        Calculates a timed viseme sequence mapping text characters to mouth shapes
        for real-time avatar lip-syncing over WebSockets or HTTP payloads.
        """
        clean_text = re.sub(r"[^\w\s]", "", text.upper())
        words = clean_text.split()

        if not words:
            return [{"time_ms": 0, "viseme": "viseme_sil", "duration_ms": int(estimated_duration_sec * 1000)}]

        total_chars = sum(len(w) for w in words)
        time_per_char = (estimated_duration_sec * 1000) / max(total_chars, 1)

        timeline: List[Dict[str, Any]] = []
        current_time_ms = 0

        for word in words:
            for char in word:
                viseme_code = VISEME_MAP.get(char, "viseme_DD")
                duration = max(40, int(time_per_char))

                timeline.append({
                    "time_ms": current_time_ms,
                    "viseme": viseme_code,
                    "char": char,
                    "duration_ms": duration
                })
                current_time_ms += duration

            # Insert short pause between words
            timeline.append({
                "time_ms": current_time_ms,
                "viseme": "viseme_sil",
                "duration_ms": 60
            })
            current_time_ms += 60

        return timeline

    async def synthesize_speech(
            self,
            text: str,
            voice_id: Optional[str] = None,
            speed: float = 1.0
    ) -> Dict[str, Any]:
        """
        Converts text string into synthesized speech audio (WAV/MP3 base64)
        along with viseme timing sequence for desktop avatar rendering.
        """
        selected_voice = voice_id or self.default_voice
        clean_text = text.strip()

        # Heuristic duration estimation (~15 characters per second at 1.0 speed)
        char_count = len(clean_text)
        estimated_duration = max(0.8, (char_count / 15.0) / speed)

        # Generate viseme timeline for lip-syncing
        viseme_sequence = self.generate_viseme_timeline(clean_text, estimated_duration)

        # Placeholder synthetic audio frame buffer (PCM Header + Sine Wave byte mock)
        # In production with local models (e.g. Piper TTS or Coqui), this executes local inference.
        mock_pcm_data = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00" + (
                    b"\x00" * 1024)
        audio_b64 = base64.b64encode(mock_pcm_data).decode("utf-8")

        return {
            "text": clean_text,
            "voice_id": selected_voice,
            "audio_b64": audio_b64,
            "format": "audio/wav",
            "duration_seconds": round(estimated_duration, 2),
            "sample_rate": self.sample_rate,
            "viseme_sequence": viseme_sequence
        }

    async def synthesize_and_broadcast(
            self,
            text: str,
            avatar_service: Any,  # This will be the AvatarConnectionManager
            voice_id: Optional[str] = None,
            speed: float = 1.0
    ) -> None:
        """
        Synthesizes speech and immediately pushes the payload
        to the provided WebSocket avatar service.
        """
        if not avatar_service:
            logger.warning("[SpeechEngine] No avatar_service provided. Skipping broadcast.")
            return

        try:
            # Generate the audio and visemes
            tts_data = await self.synthesize_speech(text, voice_id, speed)

            # Construct the inner payload data
            payload_data = {
                "chunk_id": 1,
                "audio_b64": tts_data.get("audio_b64", ""),
                "sample_rate": tts_data.get("sample_rate", self.sample_rate),
                "visemes": tts_data.get("viseme_sequence", []),
                "text_segment": text
            }

            # Use push_event instead of broadcast
            await avatar_service.push_event("speech_chunk", payload_data)
            logger.info(f"[SpeechEngine] Pushed speech payload for text: '{text[:20]}...'")

        except Exception as exc:
            logger.error(f"[SpeechEngine] Broadcaster failed: {exc}")

    async def transcribe_audio(
            self,
            audio_bytes: bytes,
            content_type: str = "audio/wav",
            language: Optional[str] = "en"
    ) -> Dict[str, Any]:
        """
        Transcribes inbound raw audio bytes to natural language text (STT).
        In production with local models (e.g. Whisper.cpp or Faster-Whisper), this runs local STT.
        """
        byte_length = len(audio_bytes)
        logger.info(f"[SpeechEngine] Transcribing audio buffer: {byte_length} bytes ({content_type})")

        if byte_length == 0:
            return {"text": "", "confidence": 0.0, "language": language}

        # Mock transcription response structure ready for Whisper engine integration
        return {
            "text": "Charon, verify system health and diagnostic logs.",
            "confidence": 0.96,
            "language": language or "en",
            "audio_bytes_processed": byte_length
        }