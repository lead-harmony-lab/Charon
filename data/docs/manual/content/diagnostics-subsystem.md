### System Diagnostics Subsystem

**Purpose**
The Diagnostics subsystem provides real-time observability into the Charon Daemon. It bridges the gap between historical system logs (REST) and live agent execution telemetry (WebSockets).

**Architecture Controller**
The primary orchestrator is `SystemDiagnostics.tsx`, which manages local state (`activeSubTab`) to switch between the live `BlackboardObserver` and the historical `AuditLedger`.