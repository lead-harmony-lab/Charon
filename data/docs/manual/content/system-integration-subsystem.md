### System & Integration Subsystem

**Purpose**
This subsystem handles the lower-level operational interfaces of the Charon Daemon, providing control over background OS services, desktop environment inter-process communication (IPC), and real-time visualization of the proactive concierge avatar.

**Architecture Controller**
The `IntegrationMatrix.tsx` component acts as the main control panel, using local state (`activeSubTab`) to route users between the `SystemdControl` and `GnomeIPC` views.