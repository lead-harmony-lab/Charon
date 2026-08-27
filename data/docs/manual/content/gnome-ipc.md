### Desktop IPC Dispatcher

**Purpose & Capabilities**
Provides a raw testing interface for dispatching payloads to the native desktop environment (e.g., GNOME HUD notifications, overlay triggers).

**Technical Details**
Users construct a raw JSON payload in a monospace `<textarea>`. On submission, the component parses the string to validate JSON integrity before dispatching it to the daemon via `POST /v1/system/ipc/send`. UI state provides immediate success/failure feedback for the dispatch operation.