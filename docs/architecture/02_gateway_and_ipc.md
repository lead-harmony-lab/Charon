# Gateway, IPC & Transport Architecture

**File Path:** `docs/architecture/02_gateway_and_ipc.md`

**System Component:** FastAPI Gateway, Asynchronous Task Queue, D-Bus System Service, WebSocket Event Bus, and Security Middleware

**Target Modules:** `charon/daemon.py`, `charon/gateway/`, `charon/dbus_server.py`, `charon/sdk.py`, `charon/cli.py`

**Protocol Specifications:** Gateway v3.1.0 / REST v1 / WebSockets / D-Bus `org.charon.Service`

---

## 1. Gateway & Daemon Architecture (`charon/daemon.py`, `charon/gateway/core.py`)

The API gateway hosts Charon’s primary communication layer under daemon version `3.1.0`. Access is controlled via constant-time header key checking alongside cross-origin resource sharing controls.

