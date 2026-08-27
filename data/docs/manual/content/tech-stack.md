### Technology Stack Overview

**Updating**
* Navigate to the dashboard root directory `Charon/charon/gateway/static/dashboard_v2` and run:
```bash
npm run build
```
Navigate to http://localhost:8000/ to view the dashboard or right-click on the desktop avatar and select `Charon Control`

**Frontend Core**
* **React 18 & TypeScript**: Single-page application framework delivering type-safe component state and UI rendering.
* **React Markdown & Prism**: Client-side markdown rendering using `react-markdown` and `react-syntax-highlighter` (`oneDark` theme) for code syntax highlighting.

**State & Drag-and-Drop**
* **Native Drag & Drop API**: Native HTML5 DnD pure functions (`removeNode`, `insertNode`, `isDescendant`) for recursive tree manipulation without external library bloat.

**Networking & Transport**
* **REST Transport (`authFetch`)**: Custom fetch wrapper injecting `X-API-Key` headers, parsing raw error responses, and managing `localStorage` persistence (`charon_api_key`).
* **Real-time Telemetry (`CharonStream`)**: Persistent WebSocket client operating at `/v1/ws` with ping loops (5s), auto-reconnect routines (3s), and pub/sub event routers.

**Backend Core**
* **Charon Daemon**: Python and Node daemon managing state orchestration, agent communication, and system diagnostics.

