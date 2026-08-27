### Real-time Telemetry (`CharonStream.ts`)

Manages persistent WebSocket connection at `/v1/ws`:

* **Heartbeat**: Ping loop every 5 seconds
* **Reconnection**: Automatic retry loop every 3 seconds
* **Pub/Sub System**: Event listeners register callbacks to specific event frames or wildcard (`*`) streams