### Systemd Control

**Data Flow & State**
Provides a UI to monitor and manipulate system background services. On mount, it fetches the list of configured daemon services via `GET /v1/system/units`.

**Mutation Operations**
Each unit card dynamically renders 'Start', 'Stop', or 'Restart' buttons based on its current `active` boolean. Clicking an action triggers a `POST /v1/system/units/{unitName}/{action}` request, followed by an immediate re-fetch to synchronize the UI state with the backend systemd manager.