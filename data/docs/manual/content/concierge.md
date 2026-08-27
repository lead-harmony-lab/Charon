The Concierge subsystem serves as the situational UX, sensory layer, and interaction face of the Charon harness. Designed after an elite executive concierge, it bridges low-level system telemetry with high-level conversational AI and multimodal feedback.

## Key Submodules

| Module | Core Responsibility | Primary Files |
| :--- | :--- | :--- |
| **Orchestration** | Manages biological temporal loops, task evaluation, and briefing generation. | `core.py`, `scheduler.py` |
| **Sensory Ingress** | Samples IDE buffers, window states, and system load; manages vector memory. | `telemetry.py`, `memory.py` |
| **Speech & Persona** | Audio STT/TTS synthesis, viseme calculation, and stoic persona enforcement. | `speech.py`, `prompts.py` |
| **Guardrails & Routing** | Structured proposal schemas, deduplication, and suppression logic. | `schemas.py`, `constants.py` |