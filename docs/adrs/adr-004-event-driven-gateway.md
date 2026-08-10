Status: Accepted

Date: 2026-07-30

Context:
Multiple frontends (GNOME Shell extensions, desktop UI, charon CLI) need real-time streaming logs, task progress updates, and prompt ingestion without blocking long-running orchestration loops.

Decision:
Expose a unified FastAPI gateway backed by an internal asyncio.Queue worker loop and WebSocket event broadcasting (EventEmitter). WebSockets handle bidirectional real-time events (token streaming, gatekeeper prompts), while HTTP endpoints accept task submissions.

Consequences:

    Positive: Completely decouples network ingress/egress from LLM inference and agent execution pipelines; enables multi-client monitoring.

    Negative: Requires strict state management across clients and handling disconnected WebSocket connections during task execution.
