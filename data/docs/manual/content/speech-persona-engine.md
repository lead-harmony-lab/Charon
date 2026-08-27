The presentation layer governs Charon's interaction style, voice capabilities, and avatar visual feedback.

## Persona Enforcement (`prompts.py`)

* **Tone Constraints:** Enforces a concise, stoic, and highly competent conciergelike voice across all interactions.
* **Contextual Formatting:** Strips conversational filler and prioritizes actionable data formatting.

## Speech Synthesis & Audio Pipeline (`speech.py`)

* **Speech-to-Text (STT):** Transcribes inbound voice commands via local Whisper models.
* **Text-to-Speech (TTS):** Generates streaming audio responses for quick turnarounds.
* **Viseme Synchronizer:** Computes precise facial viseme timing markers alongside generated audio for real-time visual avatar lipsync.