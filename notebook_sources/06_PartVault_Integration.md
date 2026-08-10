# Subsystem Domain Context: 06_PartVault_Integration
> **Generated:** 2026-08-09 18:25 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `Dynamic-Skill-Bus` | **Commit:** `13ca7e3`

---

## Target File: `/home/godvalve/Projects/Tools/PartVault/README.md`

```markdown
# Title

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/Database Structure.md`

```markdown
# Database Structure
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/ARCHITECTURE.md`

```markdown
# PartVault Architecture Specification

* **Document Version:** 1.1.0
* **Last Updated:** 2026-07-28 17:05:00 MST
* **Status:** Approved
* **Target Environment:** GNOME / GTK4 / Libadwaita (Python 3.12 via `uv`)

---

## 1. High-Level Architecture Overview

PartVault is a desktop inventory and catalog management tool built for GNOME environments. It integrates with an external background daemon (`charond`) via a REST/WebSocket gateway for real-time AI spec assistance, automated audit tasks, and physical hardware control. Both PartVault and `charond` share concurrent, process-safe access to a local SQLite database (`quartermaster.db`) operating in WAL mode.

```
                    +-----------------------------------+
                    |       PartVault Application       |
                    |    (GTK4 / Libadwaita UI Thread)  |
                    +-----------------+-----------------+
                                      |
               +----------------------+----------------------+
               |                                             |
  +------------v------------+                   +------------v------------+
  |     Navigation Split    |                   |    CharonConsoleView    |
  |   (Inventory + Detail)  |                   |    (Assistant Drawer)   |
  +------------+------------+                   +------------+------------+
               |                                             |
  +------------v------------+                   +------------v------------+
  |    InventoryDatabase    |                   |     CharonSDKClient     |
  |  (SQLite DAO w/ WAL)    |                   | (Async Thread + Buffer) |
  +------------+------------+                   +------------+------------+
               |                                             |
  ~/.local/share/partvault/                           REST / WebSocket
      quartermaster.db                                   (/v1/charond)
               ^                                             ^
               |                                             |
               +----------------- charond -------------------+
                            (Shared WAL Access)

```

---

## 2. Core Subsystems

### 2.1 Presentation & Shell Layer

* **`partvault/main.py`:** Handles `Adw.Application` lifecycle, single-instance signaling, and clean thread teardown on exit.
* **`../../partvault/ui/window.py`:** Standardizes window constraints and hosts the dual-split view container (`Adw.OverlaySplitView` wrapping `Adw.NavigationSplitView`).
* **`../../partvault/ui/views/inventory_view.py`:** Virtualized `Gtk.ListView` with dynamic client-side filtering over `Gio.ListStore`.
* **`../../partvault/ui/views/detail_view.py`:** Responsive spec page constrained with `Adw.Clamp` and direct observer binding to model state.
* **`../../partvault/ui/views/console_view.py`:** Real-time AI stream renderer using `Gtk.TextBuffer` with Pango text tags and interactive Gatekeeper intercept banners.

### 2.2 Domain & Persistence Layer

* **`partvault/models/part.py`:** Reactive `PartModel` subclassing `GObject.Object` with typed `GObject.Property` attributes.
* **`partvault/db.py`:** Direct SQLite Data Access Object (`InventoryDatabase`) managing `quartermaster.db`. Operates in **WAL mode** with 5-second busy timeouts and immediate transaction isolation to allow concurrent multi-process reads and writes with `charond`.

### 2.3 Integration Layer

* **`partvault/sdk_client.py`:** Threaded `asyncio` client managing HTTP REST requests (`httpx`) and continuous WebSocket event streams (`websockets`). Incorporates an in-memory token delta ring buffer flushed to the GTK thread at ~30 FPS (33ms) via `GLib.idle_add()` to prevent UI event queue saturation.

---

## 3. Architecture Decision Records (ADR Index)

All major technical decisions are formally recorded in `docs/architecture/adr/`.

| ID | Title | Summary / Focus Area |
| --- | --- | --- |
| **[ADR-0001](https://www.google.com/search?q=./adr/0001-use-uv-for-dependency-management.md)** | `uv` Package Management | Fast, deterministic environment setup via `pyproject.toml` and `uv.lock`. |
| **[ADR-0002](https://www.google.com/search?q=./adr/0002-dbus-ipc-integration.md)** | Gateway Integration Architecture | Async REST + WebSocket communication client (`CharonSDKClient`). |
| **[ADR-0003](https://www.google.com/search?q=./adr/0003-headless-gui-testing-strategy.md)** | Headless GUI Testing Strategy | E2E and GTK layout verification inside `Xvfb` display servers. |
| **[ADR-0004](https://www.google.com/search?q=./adr/0004-lightweight-sqlite-dao-over-heavy-orm.md)** | SQLite WAL & Multi-Process DAO | Sub-millisecond direct SQL persistence with WAL mode for process-safe concurrent access with `charond`. |
| **[ADR-0005](https://www.google.com/search?q=./adr/0005-asyncio-daemon-thread-with-glib-dispatch.md)** | Concurrency & GLib Dispatch | Non-blocking background event loop with safe GTK main-thread marshaling. |
| **[ADR-0006](https://www.google.com/search?q=./adr/0006-user-space-xdg-desktop-integration.md)** | XDG Standard Compliance | User-space storage (`~/.local/share/partvault`) and Freedesktop shortcuts. |
| **[ADR-0007](https://www.google.com/search?q=./adr/0007-gobject-subclassing-for-domain-models.md)** | GObject Domain Models | Native GTK selection, filtering, and reactive UI property bindings. |
| **[ADR-0008](https://www.google.com/search?q=./adr/0008-realtime-console-and-gatekeeper-ui.md)** | Real-time Console & Intercepts | Streaming text delta rendering and interactive physical authorization banners. |
| **[ADR-0009](https://www.google.com/search?q=./adr/0009-dual-split-view-shell-architecture.md)** | Dual-Split View Layout | Responsive GNOME multi-column master-detail layout with an AI drawer. |
| **[ADR-0010](https://www.google.com/search?q=./adr/0010-token-streaming-ring-buffer-and-render-throttling.md)** | Token Streaming Ring Buffer | Frame-throttled ~30 FPS delta flusher to protect GTK main loop performance. |

---

## 4. Concurrency & Threading Model

```
       [ Background Async Thread ]                        [ GTK Main Thread ]
  +-----------------------------------+          +-----------------------------------+
  | asyncio Event Loop                |          | GLib Main Loop                    |
  | - REST Requests                   |          | - UI Event Handling               |
  | - WebSocket Recv                  |          | - TextBuffer Rendering            |
  | - Token Delta Ring Buffer         |          | - Widget & Property Updates       |
  | - 33ms Flusher Loop               | -- GLib.idle_add ->                          |
  +-----------------------------------+          +-----------------------------------+
                    |                                              |
                    +-------------- quartermaster.db --------------+
                               (SQLite WAL Concurrency)

```

1. **Network Isolation & Ring Buffering:** Network I/O and WebSocket stream parsing execute inside an `asyncio` event loop on a background thread. Streaming deltas (`stream_delta`, `console_chunk`, `agent_delta`) append into task-keyed memory buffers.
2. **Frame-Throttled UI Marshaling:** A background loop flushes accumulated text deltas to the GTK main loop at ~30 FPS (every 33ms) via `GLib.idle_add()`. Non-stream events and task completions trigger an immediate flush to maintain message sequence ordering.
3. **Multi-Process Persistence Safety:** Database access from both the GTK thread and `charond` daemon process utilizes SQLite Write-Ahead Logging (WAL) with `busy_timeout=5000ms` and immediate transaction isolation, preventing process lock collisions.
4. **Shutdown Teardown:** `PartVaultApplication.do_shutdown()` flushes all unrendered stream buffers, cancels pending async tasks, and stops the event loop thread cleanly prior to exit.

---

## 5. Testing & Verification

* **Unit Tests (`pytest`):** Validates database CRUD and multi-process upserts (`tests/test_db.py`), domain model behavior (`tests/test_part_model.py`), and SDK ring buffer streaming (`tests/test_sdk_client.py`).
* **Headless Integration (`Xvfb`):** End-to-end execution script (`scripts/test_headless_e2e.py`) verified in displayless environments using `bin/run-headless-tests.sh`.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0001-use-uv-for-dependency-management.md`

```markdown
# 1. Use uv for Dependency Management and Lockfile Reproducibility

* **Status:** Accepted
* **Date:** 2026-07-26
* **Deciders:** @godvalve

## Context
PartVault relies on several Python packages (`httpx`, `websockets`, `pytest`, GTK bindings). Standard `pip` and `requirements.txt` lack fast lockfile generation, leading to non-reproducible local/CI environments and slow build times in GitHub Actions.

## Considered Options
* **Option 1:** Standard `pip` + `requirements.txt`
* **Option 2:** `poetry` or `pipenv`
* **Option 3:** `uv` by Astral

## Decision
We decided to adopt **`uv`** as the primary package manager and runtime harness (`pyproject.toml` + `uv.lock`).

`uv` provides near-instant environment creation, cross-platform deterministic lockfiles, and direct integration with modern Python tooling without requiring heavy OS-level runtime dependencies.

## Consequences

### Positive
* CI workflow execution (`.github/workflows/ci.yml`) is significantly faster.
* Environment reproducibility across developer Ubuntu machines and CI containers via `uv.lock`.
* Unified project configuration inside standard `pyproject.toml`.

### Negative / Trade-offs
* Developers working on PartVault must have the `uv` CLI binary installed locally.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0002-dbus-ipc-integration.md`

```markdown
# 2. Migrate Charon AI Gateway Integration from Native D-Bus to HTTP/WebSockets

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
Originally, PartVault communicated with the Charon service via native system D-Bus IPC (`org.charon.Service`). While fast locally, D-Bus imposed critical limitations:
1. Thread-blocking calls froze the GTK UI.
2. Restricted strictly to local-machine execution.
3. Rigid payload structures made real-time LLM token streaming difficult.

## Considered Options
* **Option 1:** Retain native D-Bus IPC with asynchronous GLib worker threads.
* **Option 2:** Migrate to HTTP/1.1 REST + WebSockets via FastAPI gateway.

## Decision
We chose **Option 2 (HTTP/1.1 REST + WebSockets)** implemented via `partvault.sdk_client.CharonSDKClient`.

This allows real-time token streaming (`task_stream`), multi-agent triage, human-in-the-loop gatekeeper intercepts, and remote network gateway deployments.

## Consequences

### Positive
* Non-blocking real-time streaming directly into PartVault views (`console_view.py`).
* Flexibly run Charon either on `localhost` or on a remote GPU server.

### Negative / Trade-offs
* Increased UI threading complexity: GTK4 is not thread-safe, forcing all incoming WebSocket events to be explicitly marshaled via `GLib.idle_add`.
* Requires managing network connectivity and reconnect logic in `sdk_client.py`.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0003-headless-gui-testing-strategy.md`

```markdown
# 3. Headless GUI Testing Strategy for GTK4 and CI Integration

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
GTK applications require an active X11 or Wayland display server to render widgets and handle events. Running automated end-to-end (E2E) tests in displayless CI environments (e.g., GitHub Actions) causes GUI tests to crash or skip execution.

## Considered Options
* **Option 1:** Restrict testing strictly to headless unit tests (`test_db.py`, `test_part_model.py`) and bypass UI automation entirely.
* **Option 2:** Use `Xvfb` (X Virtual Framebuffer) alongside dedicated headless execution scripts (`scripts/test_headless_e2e.py` and `bin/run-headless-tests.sh`).

## Decision
We chose **Option 2**.

We adopt a **tiered testing strategy**:
1. **Unit & Integration Layer (`pytest`):** Non-UI logic, database operations, and async client mocks in `tests/` are executed via `pytest` for rapid feedback.
2. **Headless E2E GUI Layer (Standalone Script):** GTK4/Libadwaita widget hierarchy, view initialization, and window lifecycle are verified using a standalone Python script (`scripts/test_headless_e2e.py`) executed within an isolated `xvfb-run` + `dbus-run-session` wrapper (`bin/run-headless-tests.sh`).

*Note: The E2E script intentionally bypasses `pytest` to avoid test runner framework overhead inside the virtual display buffer.*

## Implementation Details

```
           +-------------------------------------------------------+
           |                  Testing Architecture                 |
           +---------------------------+---------------------------+
                                       |
                +----------------------+----------------------+
                |                                             |
 +--------------v-------------+                 +-------------v--------------+
 |       Pytest Suite         |                 |    Headless E2E Suite      |
 |         (`tests/`)         |                 | (`test_headless_e2e.py`)   |
 +--------------+-------------+                 +-------------+--------------+
                |                                             |

```

* `test_db.py` (SQLite DAO)                     - Wrapped in `xvfb-run`
* `test_part_model.py` (GObject)                - Executes GTK4 / Libadwaita
* `test_sdk_client.py` (Async)                  - Standalone `assert` execution

## Consequences

### Positive
* High-confidence automated coverage for UI component instantiation, view routing, and event handling on every pull request.
* Fast, lightweight execution without `pytest` framework overhead during virtual display setup.
* Developers can run `bin/run-headless-tests.sh` locally without disrupting active desktop windows.

### Negative / Trade-offs
* Requires `xvfb` to be installed as a system dependency in CI runner images and local developer environments.
* Minor startup overhead when launching `dbus-run-session` and `Xvfb`.

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0004-lightweight-sqlite-dao-over-heavy-orm.md`

```markdown
# 4. Use Embedded SQLite with Lightweight DAO Layer Over Heavy ORM

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve
* **Impacted Subsystems:** Persistence Layer (`partvault/db.py`), `charond` Daemon Interface

---

## Context

PartVault requires local persistence for parts inventory, component metadata, and system state. Beyond standard desktop UI interactions, the background multi-agent orchestrator (`charond`) must concurrently query, audit, and mutate records in the shared database (`quartermaster.db`).

We evaluated whether to introduce a heavy Object-Relational Mapper (ORM) like SQLAlchemy or keep data access minimal, as well as how to handle concurrent database access across process boundaries without incurring locking deadlocks (`sqlite3.OperationalError: database is locked`).

---

## Considered Options

* **Option 1:** Full ORM framework (SQLAlchemy / Peewee) with standard rollback journal logging.
* **Option 2:** Standard library `sqlite3` wrapped in a lightweight Data Access Object (`partvault/db.py`) and domain model (`partvault/models/part.py`), configured with multi-process Write-Ahead Logging (WAL) pragmas.

---

## Decision

We chose **Option 2 (SQLite + lightweight DAO with WAL concurrency)**.

Standard `sqlite3` keeps initialization instantaneous, avoids heavy external runtime dependencies, and simplifies packaging via `pyproject.toml`. To support concurrent read/write operations from both `PartVault` (GTK UI) and `charond` (daemon process) against the same database file, the connection layer in `db.py` enforces the following concurrency standards:

1. **Write-Ahead Logging (WAL Mode):** `PRAGMA journal_mode = WAL;` allows simultaneous readers while a write operation is active.
2. **Synchronous Normal:** `PRAGMA synchronous = NORMAL;` optimizes write throughput without sacrificing WAL crash safety.
3. **Busy Timeout Handling:** `PRAGMA busy_timeout = 5000;` configures SQLite connections to wait up to 5 seconds for write locks to clear before failing.
4. **Immediate Transaction Locks:** Connections execute write operations using `isolation_level="IMMEDIATE"` to acquire write locks at the start of a transaction, preventing cross-process deadlocks.
5. **Atomic Operations:** Provide `upsert_part()` methods using SQLite `ON CONFLICT` clauses for clean agent data ingestion.

---

## Consequences

### Positive

* **Zero ORM Overhead:** Zero third-party dependency footprint for core persistence; instantaneous startup and low memory footprint.
* **Multi-Process Concurrency:** Non-blocking simultaneous read access during `charond` background sync tasks.
* **Predictable Performance:** Sub-millisecond direct query execution with explicit indexing on high-frequency search columns (`category`, `bin_location`).
* **Testability:** Database connection lifecycle is easily mockable in `tests/test_db.py`.

### Negative / Trade-offs

* **Manual Schema Management:** Database schema updates and migrations must be handled manually inside `db.py` rather than using automated migration engines (e.g., Alembic).
* **Strict Transaction Scoping:** All write operations must remain short-lived within connection contexts to ensure locks are relinquished promptly for competing processes.
* **Raw SQL Maintenance:** Complex multi-table relational queries must be written in raw SQL.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0005-asyncio-daemon-thread-with-glib-dispatch.md`

```markdown
# 5. Asyncio Background Daemon Threading with GLib Dispatch for UI Responsiveness

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
GTK4 runs on a single main loop thread. Real-time network protocols (such as WebSocket streaming from the Charon AI Gateway) require event loops (`asyncio`) that can block the GTK main loop if run on the primary thread, causing the desktop interface to freeze.

## Considered Options
* **Option 1:** `asyncio` integration via third-party GLib event loop drivers (e.g., `gbulb`).
* **Option 2:** Running a dedicated background daemon thread executing an `asyncio` loop in `CharonSDKClient`, dispatching UI state changes back to the main thread via `GLib.idle_add()`.

## Decision
We chose **Option 2**.

Spawning a dedicated daemon thread inside `partvault/sdk_client.py` keeps the async networking layer completely decoupled from GTK. All network traffic processes independently, and UI updates are explicitly marshaled to the GTK thread via `GLib.idle_add()`.

## Consequences

### Positive
* Guaranteed 60 FPS smooth desktop interface responsiveness, even during heavy WebSocket token streaming.
* Clean separation of concern: network layer (`sdk_client.py`) has zero dependency on UI view widgets.

### Negative / Trade-offs
* Developers must scrupulously wrap UI update callbacks in `GLib.idle_add()` to prevent multithreaded GTK memory corruption.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0006-user-space-xdg-desktop-integration.md`

```markdown
# 6. User-Space XDG Desktop Integration Strategy

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
PartVault is a Linux desktop application requiring OS integration (application menu shortcuts, icon rendering, launcher scripts). We need an installation strategy that works on standard Linux distributions (Ubuntu/Debian) without forcing root (`sudo`) privileges or complex distribution packages (Deb/RPM/Flatpak) during early development.

## Considered Options
* **Option 1:** Traditional root system package installation (`/usr/bin`, `/usr/share/applications`).
* **Option 2:** Containerized application distribution (Flatpak or Snap).
* **Option 3:** User-space XDG spec installation targeting `~/.local/share/` via installer scripts (`install.sh`, `bin/install-desktop-entry.sh`).

## Decision
We chose **Option 3 (User-Space XDG Integration)**.

By leveraging standard XDG directory paths (`~/.local/share/applications` and `~/.local/share/icons/hicolor/scalable/apps`), PartVault can be installed, updated, and launched seamlessly without requiring elevated `root` permissions.

## Consequences

### Positive
* Non-destructive setup: installs entirely within the user's home directory.
* Simple testing and development loop via `bin/update-desktop-entry.sh`.
* Zero system-level dependency pollution.

### Negative / Trade-offs
* Multi-user system installations require running the installer script separately per user account.
* Desktop menu databases must be manually updated using `update-desktop-database` during script execution.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0007-gobject-subclassing-for-domain-models.md`

```markdown
# 7. Subclass GObject.Object for Domain Data Models

* **Status:** Accepted
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
GTK4 high-performance view widgets (`Gtk.ListView`, `Gtk.ColumnView`, `Gtk.DropDown`) rely on GLib's model-view paradigm (`Gio.ListStore`). These widgets require data items to be `GObject.Object` instances to enable automatic UI property bindings and reactive element re-rendering.

We needed to decide whether to separate domain models from GTK or integrate them directly.

## Considered Options
* **Option 1:** Define domain entities as pure Python `@dataclass` or Pydantic models, wrapping them in custom `GObject` adapters before feeding them to UI views.
* **Option 2:** Inherit domain models directly from `GObject.Object` using PyGObject property definitions (`partvault/models/part.py`).

## Decision
We chose **Option 2 (Direct GObject Subclassing)**.

By subclassing `GObject.Object` directly on `PartModel`, model instances can be inserted directly into `Gio.ListStore` collections. UI elements bind to model properties (e.g., `notify::quantity`), automatically updating the interface when underlying data changes without requiring intermediate conversion layers.

## Consequences

### Positive
* Eliminates adapter boilerplate between the data layer and GTK views.
* Native GTK4 reactive data binding out of the box.
* Dictionary serialization (`to_dict()` and `from_dict()`) maintains simple interoperability with SQLite (`db.py`) and JSON APIs (`sdk_client.py`).

### Negative / Trade-offs
* Introduces a hard dependency on `PyGObject` (`gi.repository.GObject`) within the core domain model, meaning unit tests (`test_part_model.py`) must run in an environment with PyGObject installed.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0008-realtime-console-and-gatekeeper-ui.md`

```markdown
# 8. Real-time Console Delta Streaming and Gatekeeper Intercept Protocol

* **Status:** Proposed
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
The Charon gateway (`charond`) transmits streaming LLM responses and requires human-in-the-loop authorization ("Gatekeeper") for high-risk physical inventory operations. The GTK user interface must render text deltas in real-time without blocking the UI main thread and present interactive authorization dialogs.

## Decision
1. **Delta Rendering:** `CharonConsoleView` listens to WebSocket events (`task_stream`, `agent_log`) via `CharonSDKClient` and appends streaming text directly to a `Gtk.TextBuffer` using Pango styling tags (`tag_user`, `tag_charon`, `tag_system`, `tag_error`).
2. **Interactive Gatekeeper Intercepts:** When a `gatekeeper_intercept` event is dispatched, the console reveals an embedded `Adw.Card` action row banner displaying the pending action and decision buttons ("Proceed" / "Cancel").
3. **Response Protocol:** Triggering a decision calls `sdk_client.respond_gatekeeper_async()` to transmit authorization decisions asynchronously back to `/v1/gatekeeper/respond`.

## Consequences
### Positive
* High-responsiveness streaming output without UI frame drops or lag.
* Unambiguous physical safety prompts for critical human-in-the-loop decisions.
* Complete decoupling of WebSocket stream parsing from UI layout rendering.

### Negative
* Console text buffer requires auto-scrolling management using `Gtk.TextMark` to maintain viewport tracking during high-frequency stream events.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0009-dual-split-view-shell-architecture.md`

```markdown
# 9. Dual-Split View Shell Architecture

* **Status:** Proposed
* **Date:** 2026-07-28
* **Deciders:** @godvalve

## Context
PartVault needs to present a responsive master-detail inventory catalog alongside an expandable, real-time AI assistant drawer. Using floating modal windows or static panes degrades the desktop experience on varied display sizes.

## Decision
We implemented a nested container layout utilizing two specialized Libadwaita split containers:
1. **Outer Shell (`Adw.OverlaySplitView`):** Houses the main application content in the primary view and places `CharonConsoleView` inside the sidebar drawer (collapsible via header bar toggle).
2. **Inner Content (`Adw.NavigationSplitView`):** Hosts `InventoryView` (master sidebar) and `DetailView` (detail page) to deliver native GNOME multi-column responsive navigation.

## Consequences
### Positive
* Follows GNOME Human Interface Guidelines (HIG) for adaptive desktop displays.
* Clean separation of concerns between catalog browsing and AI interaction.
* `Adw.Clamp` in `DetailView` maintains readable text bounds regardless of window expansion.

### Negative
* Requires careful event/signal propagation between outer window controllers and inner child views.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/0010-token-streaming-ring-buffer-and-render-throttling.md`

```markdown
# ADR-0010: Token Delta Ring Buffer and Frame-Throttled UI Dispatching

* **Status:** Accepted
* **Impacted Components:** `partvault/sdk_client.py`, `../../../partvault/ui/views/console_view.py`

## Context
When `charond` streams real-time AI responses via WebSocket, tokens can arrive at speeds exceeding 100+ events per second. Posting each token immediately to GTK's main thread via `GLib.idle_add()` floods the GLib event queue, resulting in excessive context switching, CPU spikes, and main thread UI stutters.

## Decision
1. Introduce a streaming delta buffer (`_stream_buffers`) within `CharonSDKClient`.
2. High-frequency stream events (`stream_delta`, `token_stream`, `console_chunk`, `agent_delta`) append text deltas into an in-memory task dictionary on the `asyncio` loop thread rather than immediately dispatching to GLib.
3. Run a dedicated background flusher loop (`_stream_flusher_loop`) that drains accumulated buffers to GTK via `GLib.idle_add()` at fixed intervals of 33ms (~30 FPS).
4. Non-stream events (e.g., `task_completed`, `gatekeeper_intercept`) trigger an immediate synchronous flush of pending deltas for that task ID prior to event dispatch to maintain chronological order in the UI.

## Consequences
* **Positive:** Main GTK thread frame rates remain rock-solid at 60 FPS even during heavy multi-agent streaming output. Reduces GLib event queue overhead by >80%.
* **Negative:** Introduces a maximum perceptual display lag of 33ms for incoming streaming text deltas.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/adr/INDEX.md`

```markdown
# Architecture Decision Record (ADR) Index & Summary Log

* **Repository:** `PartVault`
* **Path:** `docs/architecture/adr/`
* **Format Standard:** Extended Nygard Format (LLM Context-Optimized)
* **Last Updated:** 2026-07-28 16:55:00 MST

---

## 1. Quick Reference Matrix

| ID | Document Title | Status | Primary Target / Subsystem | Key Tech / Pattern |
| --- | --- | --- | --- | --- |
| [0001](https://www.google.com/search?q=./0001-use-uv-for-dependency-management.md) | `0001-use-uv-for-dependency-management.md` | **Accepted** | Packaging / Tooling | `uv`, `pyproject.toml` |
| [0002](https://www.google.com/search?q=./0002-dbus-ipc-integration.md) | `0002-dbus-ipc-integration.md` | **Accepted** | Daemon Integration | REST / WS Gateway (`charond`) |
| [0003](https://www.google.com/search?q=./0003-headless-gui-testing-strategy.md) | `0003-headless-gui-testing-strategy.md` | **Accepted** | CI / Automation | `pytest`, `Xvfb`, `dbus-run-session` |
| [0004](https://www.google.com/search?q=./0004-lightweight-sqlite-dao-over-heavy-orm.md) | `0004-lightweight-sqlite-dao-over-heavy-orm.md` | **Updated** | Persistence Layer | SQLite, WAL Mode, Concurrent DAO |
| [0005](https://www.google.com/search?q=./0005-asyncio-daemon-thread-with-glib-dispatch.md) | `0005-asyncio-daemon-thread-with-glib-dispatch.md` | **Accepted** | Concurrency / Threading | `asyncio`, `GLib.idle_add` |
| [0006](https://www.google.com/search?q=./0006-user-space-xdg-desktop-integration.md) | `0006-user-space-xdg-desktop-integration.md` | **Accepted** | Environment / Desktop | XDG Base Dir Spec |
| [0007](https://www.google.com/search?q=./0007-gobject-subclassing-for-domain-models.md) | `0007-gobject-subclassing-for-domain-models.md` | **Accepted** | Presentation Models | `GObject`, `GObject.Property` |
| [0008](https://www.google.com/search?q=./0008-realtime-console-and-gatekeeper-ui.md) | `0008-realtime-console-and-gatekeeper-ui.md` | **Accepted** | Assistant Drawer | `Gtk.TextBuffer`, WS Streaming |
| [0009](https://www.google.com/search?q=./0009-dual-split-view-shell-architecture.md) | `0009-dual-split-view-shell-architecture.md` | **Accepted** | Window Navigation | `Adw.OverlaySplitView`, `Adw.NavigationSplitView` |
| [0010](https://www.google.com/search?q=./0010-token-streaming-ring-buffer-and-render-throttling.md) | `0010-token-streaming-ring-buffer-and-render-throttling.md` | **Accepted** | SDK Streaming | Ring Buffer, 30 FPS Flusher Loop |

---

## 2. ADR Executive Summaries

### ADR-0001: Use `uv` for Dependency Management

* **File:** `docs/architecture/adr/0001-use-uv-for-dependency-management.md`
* **Status:** Accepted
* **Context:** Need fast, reproducible Python environment management for GTK4/PyGObject bindings without slow resolver bottlenecks.
* **Decision:** Adopt `uv` as the default package manager (`uv sync`, `uv run`) backed by `pyproject.toml` and `uv.lock`.
* **Consequences:** Near-instant environment setup and locking. System GTK dependencies (`PyGObject`, `Cairo`) must be passed through via system site packages when necessary.

---

### ADR-0002: IPC & Integration Architecture

* **File:** `docs/architecture/adr/0002-dbus-ipc-integration.md`
* **Status:** Accepted
* **Context:** Interface `PartVault` with the local `charond` agent background process for telemetry, spec querying, and physical hardware control.
* **Decision:** Standardize on an asynchronous REST (HTTP) + WebSocket gateway client (`CharonSDKClient`) for real-time task streaming and authorization callbacks.
* **Consequences:** Decouples UI execution from backend agent execution. Requires network error handling and reconnect logic in `sdk_client.py`.

---

### ADR-0003: Headless GUI Testing Strategy

* **File:** `docs/architecture/adr/0003-headless-gui-testing-strategy.md`
* **Status:** Accepted
* **Context:** GTK4 applications require an active display server (`X11`/`Wayland`), causing automated CI pipelines (GitHub Actions) to fail during UI tests.
* **Decision:** Adopt a tiered strategy: execute non-UI unit and client integration tests via `pytest`, while executing GTK widget hierarchy and end-to-end flow tests inside `Xvfb` and `dbus-run-session` using a standalone runner script (`scripts/test_headless_e2e.py` via `bin/run-headless-tests.sh`).
* **Consequences:** Allows 100% automated UI test execution in CI without physical display hardware. Keeps virtual display setup isolated from `pytest` runner overhead while maintaining standard `pytest` tooling for unit suites.

---

### ADR-0004: Lightweight SQLite DAO with Multi-Process WAL Access (UPDATED)

* **File:** `docs/architecture/adr/0004-lightweight-sqlite-dao-over-heavy-orm.md`
* **Status:** Accepted (Updated 2026-07-28)
* **Context:** `PartVault` (desktop UI) and `charond` (multi-agent background daemon) require simultaneous read/write access to `quartermaster.db` without locking errors or third-party ORM overhead.
* **Decision:** Implement an SQLite Data Access Object (`InventoryDatabase`) enforcing **Write-Ahead Logging (`WAL`)**, `busy_timeout = 5000ms`, `isolation_level = "IMMEDIATE"`, and atomic `upsert_part` methods.
* **Consequences:** Sub-millisecond direct query performance and deadlock-free concurrent process access. Operations must remain short-lived within connection contexts.

---

### ADR-0005: Asyncio Daemon Thread with GLib Dispatch

* **File:** `docs/architecture/adr/0005-asyncio-daemon-thread-with-glib-dispatch.md`
* **Status:** Accepted
* **Context:** Asynchronous WebSocket streaming and REST calls from `CharonSDKClient` must not block the GTK main loop (UI thread). GTK UI widgets are not thread-safe.
* **Decision:** Run an `asyncio` event loop in a background daemon thread. Post UI state updates back to the main thread exclusively using `GLib.idle_add()`.
* **Consequences:** Guaranteed 60 FPS UI responsiveness during continuous log streams. Prevents multi-threading GTK execution crashes.

---

### ADR-0006: User-Space XDG Desktop Integration

* **File:** `docs/architecture/adr/0006-user-space-xdg-desktop-integration.md`
* **Status:** Accepted
* **Context:** Application configuration, database storage, and desktop shortcuts must strictly adhere to Linux desktop standards without requiring root privileges.
* **Decision:** Store SQLite database and app data in `$XDG_DATA_HOME/partvault` (`~/.local/share/partvault`). Install user-space desktop shortcuts and icons via `bin/install-desktop-entry.sh`.
* **Consequences:** Non-intrusive installation compliant with Freedesktop.org standards. Operates entirely within user space.

---

### ADR-0007: GObject Subclassing for Domain Models

* **File:** `docs/architecture/adr/0007-gobject-subclassing-for-domain-models.md`
* **Status:** Accepted
* **Context:** Standard Python data classes do not integrate natively with GTK4 list models (`Gio.ListStore`, `Gtk.FilterListModel`) or automatic widget property bindings.
* **Decision:** Subclass `GObject.Object` for core domain entities (`PartModel` in `partvault/models/part.py`), defining field attributes as `GObject.Property`.
* **Consequences:** Enables zero-boilerplate reactive UI updates via GObject signals (`notify::quantity`). Requires PyGObject type declarations.

---

### ADR-0008: Real-time Console Delta Streaming and Gatekeeper Intercept Protocol

* **File:** `docs/architecture/adr/0008-realtime-console-and-gatekeeper-ui.md`
* **Status:** Accepted
* **Context:** Streaming AI text deltas and handling physical safety authorization ("Gatekeeper Intercepts") require real-time, non-blocking UI rendering.
* **Decision:** Render incoming WS token deltas directly into `Gtk.TextBuffer` using Pango styling tags in `CharonConsoleView`. Intercept actions dynamically render an inline `Adw.Card` authorization banner with asynchronous response handlers.
* **Consequences:** Fluid text animation and immediate human-in-the-loop authorization controls. Requires `Gtk.TextMark` scroll management.

---

### ADR-0009: Dual-Split View Shell Architecture

* **File:** `docs/architecture/adr/0009-dual-split-view-shell-architecture.md`
* **Status:** Accepted
* **Context:** Must balance an adaptive master-detail component browser with an expandable real-time AI assistant drawer across diverse screen resolutions.
* **Decision:** Nest an `Adw.NavigationSplitView` (Master: `InventoryView`, Detail: `DetailView`) inside an outer `Adw.OverlaySplitView` (Sidebar: `CharonConsoleView`).
* **Consequences:** Strict HIG compliance and seamless responsive resizing. Requires explicit signal pass-through between parent window and nested child views.

---

### ADR-0010: Token Delta Ring Buffer and Frame-Throttled UI Dispatching (NEW)

* **File:** `docs/architecture/adr/0010-token-streaming-ring-buffer-and-render-throttling.md`
* **Status:** Accepted
* **Context:** High-frequency WebSocket token streams from `charond` can saturate the GTK main event loop if every incoming token triggers a distinct `GLib.idle_add()` call, resulting in UI micro-stutters.
* **Decision:** Implement an in-memory aggregation ring buffer in `CharonSDKClient`. Delta events are buffered on the async thread and flushed to GTK at ~30 FPS (every 33ms). Intercept and non-stream completion events trigger an immediate flush to preserve event ordering.
* **Consequences:** Silky 60 FPS UI rendering regardless of LLM streaming speed. Adds ~33ms maximum latency to streaming token display.

---
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/architecture/integrations/charon_integration.md`

```markdown
# Integration Specification: Charon AI Gateway

* **Spec Version:** 3.2.0
* **Target Application:** PartVault (GTK4 / PyGObject)
* **Gateway Engine:** Charon v3.1.0 (FastAPI + WebSockets + Ollama)
* **Primary Adapter:** `partvault.sdk_client.CharonSDKClient`

---

## 1. Overview & Architectural Migration

PartVault integrates with the **Charon AI Gateway** to provide real-time multi-agent triage, proactive inventory recommendations, and automated task execution.

```text
+-----------------------------------------------------------------------+
|  PartVault UI (GTK4 Main Thread)                                      |
|   | (GLib.idle_add)                                                   |
|   v                                                                   |
|  CharonSDKClient (Background Asyncio Daemon Thread)                   |
+---------------------+-------------------------------------------------+
                      |
        +-------------+-------------+
        | HTTP REST                 | WebSockets
        v                           v
+-----------------------------------------------------------------------+
|  Charon AI Gateway (FastAPI Engine @ http://localhost:8000)          |
|   ├── Task Router & Agent Triage                                      |
|   ├── Human-in-the-Loop Gatekeeper Intercepts                         |
|   └── Ollama LLM Backend                                              |
+-----------------------------------------------------------------------+

```

### Paradigm Migration

| Metric / Feature | Legacy Paradigm | Current Paradigm (v3.2) |
| --- | --- | --- |
| **Transport** | Native D-Bus IPC (`org.charon.Service`) | HTTP/1.1 REST + WebSockets |
| **Execution** | Synchronous / Blocking threads | Asynchronous background execution |
| **Scope** | Local machine context only | Distributed / Flexible network scope |
| **Streaming** | None (Single response payload) | Real-time token delta streaming |
| **Human-in-the-Loop** | Not supported | Gatekeeper approval workflow |

---

## 2. Authentication

All authenticated requests require an API key passed via headers, query parameters, or environment variables.

* **Header Name:** `X-API-Key`
* **Query Parameter:** `api_key`
* **Environment Variable:** `CHARON_API_KEY`
* **Development Fallback:** `sk_charon_dev_key`
* **Validation:** Constant-time comparison on the gateway server.

---

## 3. REST API Contracts

* **Base URL:** `http://localhost:8000`

### 3.1 Health Check

* **Endpoint:** `GET /v1/health`
* **Authentication:** Unauthenticated

### 3.2 Submit Task

* **Endpoint:** `POST /v1/task`
* **Authentication:** Required (`X-API-Key`)
* **Request Payload:**
```json
{
  "prompt": "Inspect low stock automotive parts and generate reorder list",
  "client_id": "partvault-app",
  "agent_override": null,
  "context": { "category": "automotive" }
}

```


* **Response Payload:**
```json
{
  "task_id": "tsk_8f9a2b",
  "status": "queued",
  "assigned_agent": "inventory_agent",
  "message": "Task successfully routed to inventory_agent"
}

```



### 3.3 Gatekeeper Response

Responds to high-risk action intercepts emitted by the Charon engine.

* **Endpoint:** `POST /v1/gatekeeper/respond`
* **Authentication:** Required (`X-API-Key`)
* **Request Payload:**
```json
{
  "approval_id": "appr_9921a",
  "decision": "proceed",
  "client_id": "partvault-app",
  "notes": "Approved by local admin user"
}

```


*(Allowed `decision` enum values: `proceed`, `cancel`, `rescind`)*

---

## 4. WebSocket Event Bus

* **Endpoint:** `ws://localhost:8000/v1/ws?client_id=partvault-app&api_key=sk_charon_dev_key`

Every frame transmitted over the WebSocket conforms to the following baseline model:

```json
{
  "event_type": "string",
  "task_id": "string | null",
  "data": {}
}

```

### Event Taxonomy

| Event Type | Description | Data Payload Schema |
| --- | --- | --- |
| `task_stream` | Token/text deltas streamed live from an active LLM agent. | `{"message": "string"}` |
| `agent_log` | Internal reasoning steps, tool calls, or subshell logs. | `{"message": "string"}` |
| `concierge_suggestion` | Proactive follow-up actions generated by Charon. | `{"next_step": "str", "recommendation": "str"}` |
| `gatekeeper_intercept` | Intercept triggered when high-risk operations require human sign-off. | `{"approval_id": "string", "action": "string"}` |
| `system_alert` | Engine status alerts (e.g., Ollama offline, model loading failures). | `{"message": "string"}` |
| `task_complete` | Signals task execution completion. | `{"summary": "string", "streamed": true}` |
| `task_error` | Emitted when task processing fails unrecoverably. | `{"error": "string"}` |

---

## 5. UI Integration & Thread Safety Rules

> [!CAUTION]
> **GTK Main Loop Thread Safety**
> GTK4 is **not thread-safe**. Because WebSocket events are received inside a background `asyncio` event loop thread, **UI updates must never be invoked directly from the WebSocket callback**.

### Rule 1: Thread Marshaling (`GLib.idle_add`)

All incoming WebSocket handlers must wrap GTK interface mutations inside `GLib.idle_add`:

```python
# Correct Thread Marshaling in PartVault View
def _on_websocket_event(self, event_type: str, data: dict):
    # Dispatch UI update safely back to GTK main loop thread
    GLib.idle_add(self._update_ui_state, event_type, data)

```

### Rule 2: Stream Deduplication Contract

UI components that render `task_stream` chunks incrementally **MUST ignore** the `summary` string provided in `task_complete` if `streamed == true` (or if text chunks were already appended) to avoid duplicate text rendering.

---

## 6. SDK Adapter Architecture

The integration adapter is encapsulated in `partvault/sdk_client.py`.

```python
class CharonSDKClient:
    """
    Manages background asyncio thread loop, REST requests via httpx, 
    and persistent WebSocket event streaming.
    """
    def submit_task_async(self, prompt: str, callback=None, context=None, agent_override=None): ...
    def respond_gatekeeper_async(self, approval_id: str, decision: str, notes=None, callback=None): ...
    def register_ui_callback(self, event_type: str, callback: callable): ...
    def shutdown(self): ...

```
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/docs/database_schema.md`

```markdown
# 🗄️ Quartermaster Database Schema (`quartermaster.db`)

* **Engine:** SQLite 3
* **Path:** `~/.local/share/partvault/quartermaster.db`
* **KiCad Integration:** Exposes `v_kicad_parts` view pointing to `~/.local/share/partvault/datasheets/`

---

## 📊 Table Specifications

### TABLE: `parts`

| CID | Column Name | Data Type | Not Null | Default Value | Primary Key |
|---|---|---|---|---|---|
| 0 | `id` | `INTEGER` | False | *None* | True |
| 1 | `mpn` | `TEXT` | True | *None* | False |
| 2 | `manufacturer` | `TEXT` | False | *None* | False |
| 3 | `category` | `TEXT` | True | *None* | False |
| 4 | `sub_category` | `TEXT` | False | *None* | False |
| 5 | `description` | `TEXT` | False | *None* | False |
| 6 | `package_footprint` | `TEXT` | False | *None* | False |
| 7 | `parameters_json` | `TEXT` | False | *None* | False |
| 8 | `created_at` | `TIMESTAMP` | False | `CURRENT_TIMESTAMP` | False |

### TABLE: `inventory`

| CID | Column Name | Data Type | Not Null | Default Value | Primary Key |
|---|---|---|---|---|---|
| 0 | `id` | `INTEGER` | False | *None* | True |
| 1 | `part_id` | `INTEGER` | True | *None* | False |
| 2 | `quantity` | `INTEGER` | False | `0` | False |
| 3 | `storage_bin` | `TEXT` | True | *None* | False |
| 4 | `min_stock_alert` | `INTEGER` | False | `0` | False |
| 5 | `last_updated` | `TIMESTAMP` | False | `CURRENT_TIMESTAMP` | False |

### TABLE: `datasheets`

| CID | Column Name | Data Type | Not Null | Default Value | Primary Key |
|---|---|---|---|---|---|
| 0 | `id` | `INTEGER` | False | *None* | True |
| 1 | `part_id` | `INTEGER` | True | *None* | False |
| 2 | `file_path` | `TEXT` | True | *None* | False |
| 3 | `source_url` | `TEXT` | False | *None* | False |
| 4 | `date_acquired` | `TIMESTAMP` | False | `CURRENT_TIMESTAMP` | False |

### TABLE: `bom_items`

| CID | Column Name | Data Type | Not Null | Default Value | Primary Key |
|---|---|---|---|---|---|
| 0 | `id` | `INTEGER` | False | *None* | True |
| 1 | `project_name` | `TEXT` | True | *None* | False |
| 2 | `part_id` | `INTEGER` | True | *None* | False |
| 3 | `qty_required` | `INTEGER` | True | *None* | False |

### VIEW: `v_kicad_parts`

| CID | Column Name | Data Type | Not Null | Default Value | Primary Key |
|---|---|---|---|---|---|
| 0 | `id` | `INTEGER` | False | *None* | False |
| 1 | `mpn` | `TEXT` | False | *None* | False |
| 2 | `manufacturer` | `TEXT` | False | *None* | False |
| 3 | `category` | `TEXT` | False | *None* | False |
| 4 | `sub_category` | `TEXT` | False | *None* | False |
| 5 | `description` | `TEXT` | False | *None* | False |
| 6 | `package_footprint` | `TEXT` | False | *None* | False |
| 7 | `in_stock` | `` | False | *None* | False |
| 8 | `datasheet_path` | `` | False | *None* | False |

## ⚡ Database Indexes

| Index Name | Table | Unique |
|---|---|---|
| `idx_parts_mpn` | `parts` | True |
| `idx_parts_category` | `parts` | True |
| `idx_inventory_bin` | `inventory` | True |
| `idx_bom_project` | `bom_items` | True |

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/db.py`

```python
"""
partvault/db.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: SQLite persistence layer for PartVault inventory.
Fully aligned with Charon's live database schema (v_kicad_parts, storage_bin, last_updated)
and system metadata protocol.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from partvault.models.part import PartModel

logger = logging.getLogger("PartVault.Database")

# Canonical XDG Data Directory Resolution
XDG_DATA_HOME = Path(
    os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
).resolve()
DEFAULT_DB_PATH = XDG_DATA_HOME / "partvault" / "quartermaster.db"


class InventoryDatabase:
    """
    SQLite persistence layer for PartVault inventory.
    Configured with WAL mode and immediate lock acquisition to support concurrent
    multi-process access shared with charond and external daemon services.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Returns an SQLite connection configured with Row access, busy timeouts,
        and write isolation for multi-process safety.
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,  # Explicit connection busy timeout
            isolation_level="IMMEDIATE",  # Acquires write locks immediately
        )
        conn.row_factory = sqlite3.Row

        # Multi-process execution PRAGMAs
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        """Ensures table indexes, metadata structures, and default views exist."""
        schema_script = """
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mpn TEXT UNIQUE NOT NULL,
            manufacturer TEXT,
            category TEXT NOT NULL,
            sub_category TEXT,
            description TEXT,
            package_footprint TEXT,
            parameters_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
            quantity INTEGER DEFAULT 0 CHECK(quantity >= 0),
            storage_bin TEXT NOT NULL,
            min_stock_alert INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(part_id, storage_bin)
        );

        CREATE TABLE IF NOT EXISTS datasheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL UNIQUE,
            source_url TEXT,
            date_acquired TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS system_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_parts_mpn ON parts(mpn);
        CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
        CREATE INDEX IF NOT EXISTS idx_inventory_bin ON inventory(storage_bin);

        /* Self-healing fallback view creation for standalone execution */
        CREATE VIEW IF NOT EXISTS v_kicad_parts AS
        SELECT 
            p.id AS id,
            p.mpn AS mpn,
            p.description AS description,
            p.category AS category,
            COALESCE(SUM(i.quantity), 0) AS in_stock,
            d.file_path AS datasheet_path
        FROM parts p
        LEFT JOIN inventory i ON p.id = i.part_id
        LEFT JOIN datasheets d ON p.id = d.part_id
        GROUP BY p.id;
        """
        try:
            with self._get_connection() as conn:
                conn.executescript(schema_script)
                conn.commit()
            logger.info(f"Database connection verified at: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database schema: {e}")
            raise

    # =========================================================================
    # SYSTEM METADATA OPERATIONS (Key-Value State Tracking)
    # =========================================================================

    def set_metadata(self, key: str, value: str) -> bool:
        """Upserts a metadata key-value pair, explicitly driving updated_at."""
        query = """
        INSERT INTO system_metadata (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = CURRENT_TIMESTAMP;
        """
        try:
            with self._get_connection() as conn:
                conn.execute(query, (key, value))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Failed to set metadata '{key}': {e}")
            return False

    def get_metadata(self, key: str) -> Optional[str]:
        """Fetches a metadata value by key."""
        query = "SELECT value FROM system_metadata WHERE key = ?;"
        try:
            with self._get_connection() as conn:
                row = conn.execute(query, (key,)).fetchone()
                return row["value"] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch metadata '{key}': {e}")
            return None

    def get_all_metadata(self) -> Dict[str, str]:
        """Fetches all system metadata key-value pairs."""
        query = "SELECT key, value FROM system_metadata;"
        try:
            with self._get_connection() as conn:
                rows = conn.execute(query).fetchall()
                return {row["key"]: row["value"] for row in rows}
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch all metadata: {e}")
            return {}

    def set_last_sync_time(self, timestamp_iso: Optional[str] = None) -> bool:
        """Helper to set the last_synced_at ISO timestamp."""
        if not timestamp_iso:
            timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.set_metadata("last_synced_at", timestamp_iso)

    def get_last_sync_time(self) -> Optional[str]:
        """Helper to retrieve the last_synced_at timestamp."""
        return self.get_metadata("last_synced_at")

    # =========================================================================
    # READ OPERATIONS (Unified via v_kicad_parts & inventory)
    # =========================================================================

    def get_all_parts(self) -> List[PartModel]:
        """Fetches all inventory parts sorted by MPN."""
        query = """
        SELECT 
            v.mpn AS mpn,
            COALESCE(v.description, '') AS description,
            COALESCE(v.category, 'General') AS category,
            COALESCE(v.in_stock, 0) AS quantity,
            COALESCE(GROUP_CONCAT(DISTINCT i.storage_bin), 'Unassigned') AS bin_location,
            COALESCE(v.datasheet_path, '') AS datasheet_path
        FROM v_kicad_parts v
        LEFT JOIN inventory i ON v.id = i.part_id
        GROUP BY v.id
        ORDER BY v.mpn ASC;
        """
        parts = []
        try:
            with self._get_connection() as conn:
                rows = conn.execute(query).fetchall()
                for row in rows:
                    parts.append(PartModel.from_dict(dict(row)))
        except sqlite3.Error as e:
            logger.error(f"Error fetching parts: {e}")
        return parts

    def get_part_by_mpn(self, mpn: str) -> Optional[PartModel]:
        """Retrieves a single part by MPN."""
        query = """
        SELECT 
            v.mpn AS mpn,
            COALESCE(v.description, '') AS description,
            COALESCE(v.category, 'General') AS category,
            COALESCE(v.in_stock, 0) AS quantity,
            COALESCE(GROUP_CONCAT(DISTINCT i.storage_bin), 'Unassigned') AS bin_location,
            COALESCE(v.datasheet_path, '') AS datasheet_path
        FROM v_kicad_parts v
        LEFT JOIN inventory i ON v.id = i.part_id
        WHERE v.mpn = ?
        GROUP BY v.id;
        """
        try:
            with self._get_connection() as conn:
                row = conn.execute(query, (mpn,)).fetchone()
                if row:
                    return PartModel.from_dict(dict(row))
        except sqlite3.Error as e:
            logger.error(f"Error fetching MPN '{mpn}': {e}")
        return None

    def search_parts(self, search_term: str) -> List[PartModel]:
        """Performs a multi-column search across MPN, description, bin location, and category."""
        query = """
        SELECT 
            v.mpn AS mpn,
            COALESCE(v.description, '') AS description,
            COALESCE(v.category, 'General') AS category,
            COALESCE(v.in_stock, 0) AS quantity,
            COALESCE(GROUP_CONCAT(DISTINCT i.storage_bin), 'Unassigned') AS bin_location,
            COALESCE(v.datasheet_path, '') AS datasheet_path
        FROM v_kicad_parts v
        LEFT JOIN inventory i ON v.id = i.part_id
        WHERE v.mpn LIKE ? OR v.description LIKE ? OR i.storage_bin LIKE ? OR v.category LIKE ?
        GROUP BY v.id
        ORDER BY v.mpn ASC;
        """
        wildcard = f"%{search_term}%"
        parts = []
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    query, (wildcard, wildcard, wildcard, wildcard)
                ).fetchall()
                for row in rows:
                    parts.append(PartModel.from_dict(dict(row)))
        except sqlite3.Error as e:
            logger.error(f"Error searching parts with term '{search_term}': {e}")
        return parts

    # =========================================================================
    # WRITE OPERATIONS (Transactionally distributed across parts & inventory)
    # =========================================================================

    def upsert_part(self, part: PartModel) -> bool:
        """
        Atomically inserts or updates base part details and logs inventory count.
        Respects storage_bin and check constraints.
        """
        part_dict = part.to_dict() if hasattr(part, "to_dict") else dict(part)
        mpn = part_dict.get("mpn")
        if not mpn:
            logger.error("Cannot upsert part without an MPN.")
            return False

        category = part_dict.get("category") or "General"
        description = part_dict.get("description") or ""
        bin_loc = part_dict.get("bin_location") or "Unassigned"
        qty = max(0, int(part_dict.get("quantity", 0)))

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Upsert into parts table
                cursor.execute(
                    """
                    INSERT INTO parts (mpn, description, category)
                    VALUES (?, ?, ?)
                    ON CONFLICT(mpn) DO UPDATE SET
                        description = EXCLUDED.description,
                        category = EXCLUDED.category;
                    """,
                    (mpn, description, category),
                )

                # Fetch generated/existing part_id
                cursor.execute("SELECT id FROM parts WHERE mpn = ?;", (mpn,))
                row = cursor.fetchone()
                if not row:
                    return False
                part_id = row["id"]

                # 2. Upsert into inventory table
                cursor.execute(
                    """
                    INSERT INTO inventory (part_id, quantity, storage_bin, last_updated)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(part_id, storage_bin) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        last_updated = CURRENT_TIMESTAMP;
                    """,
                    (part_id, qty, bin_loc),
                )

                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Failed to upsert part '{mpn}': {e}")
            return False

    def update_quantity(self, mpn: str, new_quantity: int) -> bool:
        """Updates stock count for a given MPN in the inventory table."""
        new_quantity = max(0, new_quantity)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM parts WHERE mpn = ?;", (mpn,))
                part_row = cursor.fetchone()
                if not part_row:
                    logger.warning(f"Cannot update quantity. Part '{mpn}' not found.")
                    return False

                part_id = part_row["id"]
                cursor.execute(
                    """
                    UPDATE inventory 
                    SET quantity = ?, last_updated = CURRENT_TIMESTAMP 
                    WHERE part_id = ?;
                    """,
                    (new_quantity, part_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO inventory (part_id, quantity, storage_bin) 
                        VALUES (?, ?, 'Unassigned');
                        """,
                        (part_id, new_quantity),
                    )

                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update quantity for '{mpn}': {e}")
            return False

    def delete_part(self, mpn: str) -> bool:
        """Deletes a part record and cascades deletion."""
        query = "DELETE FROM parts WHERE mpn = ?;"
        try:
            with self._get_connection() as conn:
                res = conn.execute(query, (mpn,))
                conn.commit()
                return res.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete part '{mpn}': {e}")
            return False
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/main.py`

```python
import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from partvault.ui.window import PartVaultWindow

logger = logging.getLogger("PartVault.Main")


class PartVaultApplication(Adw.Application):
    """Main Adw.Application instance for PartVault."""

    def __init__(self):
        super().__init__(
            application_id="org.partvault.App",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_startup(self):
        """Called on application startup. Registers global keyboard accelerators."""
        Adw.Application.do_startup(self)

        # Map actions to standard GTK shortcuts
        self.set_accels_for_action("win.refresh", ["<Primary>r"])
        self.set_accels_for_action("win.preferences", ["<Primary>comma"])
        self.set_accels_for_action("win.about", ["F1"])

    def do_activate(self):
        """Called when the application is launched."""
        win = self.props.active_window
        if not win:
            win = PartVaultWindow(application=self)
        win.present()

    def do_shutdown(self):
        """Clean up SDK connections and background loops on app exit."""
        logger.info("PartVault application shutting down...")

        # Safely shut down SDK client across open windows
        for win in self.get_windows():
            if hasattr(win, "sdk_client"):
                logger.info("Shutting down Charon SDK Client...")
                win.sdk_client.shutdown()
            elif hasattr(win, "console_view") and hasattr(win.console_view, "sdk_client"):
                logger.info("Shutting down Charon SDK Client from console view...")
                win.console_view.sdk_client.shutdown()

        Adw.Application.do_shutdown(self)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = PartVaultApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/models/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/models/part.py`

```python
"""
partvault/models/part.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: GObject Data Model for PartVault parts, extended to map Charon's relational schema.
"""

import logging
import gi

gi.require_version("GObject", "2.0")
from gi.repository import GObject

logger = logging.getLogger("PartVault.PartModel")


class PartModel(GObject.Object):
    """
    GObject Data Model representing an individual electronic component in PartVault.
    Inherits from GObject.Object to enable native GTK4 Gtk.ListView and Gio.ListStore
    property binding and auto-updating UI tags.
    """

    # --- GObject Managed Properties ---
    mpn = GObject.Property(type=str, default="")
    manufacturer = GObject.Property(type=str, default="")
    category = GObject.Property(type=str, default="General")
    sub_category = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    package_footprint = GObject.Property(type=str, default="")
    quantity = GObject.Property(type=int, default=0)
    bin_location = GObject.Property(type=str, default="Unassigned")
    min_threshold = GObject.Property(type=int, default=2)
    datasheet_path = GObject.Property(type=str, default="")
    mouser_url = GObject.Property(type=str, default="")

    def __init__(
        self,
        mpn: str = "",
        manufacturer: str = "",
        category: str = "General",
        sub_category: str = "",
        description: str = "",
        package_footprint: str = "",
        quantity: int = 0,
        bin_location: str = "Unassigned",
        min_threshold: int = 2,
        datasheet_path: str = "",
        mouser_url: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.mpn = mpn
        self.manufacturer = manufacturer
        self.category = category
        self.sub_category = sub_category
        self.description = description
        self.package_footprint = package_footprint
        self.quantity = quantity
        self.bin_location = bin_location
        self.min_threshold = min_threshold
        self.datasheet_path = datasheet_path
        self.mouser_url = mouser_url

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    @property
    def is_low_stock(self) -> bool:
        """Returns True if stock level is at or below the threshold."""
        return self.quantity <= self.min_threshold

    def to_dict(self) -> dict:
        """Serializes the GObject instance properties into a plain dictionary."""
        return {
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "sub_category": self.sub_category,
            "description": self.description,
            "package_footprint": self.package_footprint,
            "quantity": self.quantity,
            "bin_location": self.bin_location,
            "min_threshold": self.min_threshold,
            "datasheet_path": self.datasheet_path,
            "mouser_url": self.mouser_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PartModel":
        """Factory method to construct a PartModel instance from a dictionary."""
        return cls(
            mpn=data.get("mpn", ""),
            manufacturer=data.get("manufacturer", ""),
            category=data.get("category", "General"),
            sub_category=data.get("sub_category", ""),
            description=data.get("description", ""),
            package_footprint=data.get("package_footprint", ""),
            quantity=int(data.get("quantity", data.get("in_stock", 0))),
            bin_location=data.get("bin_location", data.get("storage_bin", "Unassigned")),
            min_threshold=int(data.get("min_threshold", data.get("min_stock_alert", 2))),
            datasheet_path=data.get("datasheet_path", ""),
            mouser_url=data.get("mouser_url", data.get("source_url", "")),
        )

    def __repr__(self) -> str:
        return f"<PartModel MPN='{self.mpn}' Qty={self.quantity} Bin='{self.bin_location}'>"
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/services/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/services/charon_client.py`

```python
"""
partvault/services/charon_client.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Async Client Adapter for GTK4/Adw with Streaming Delta Aggregation,
WebSocket TelemetryBus integration, and REST synchronization hooks for charond.
"""

import asyncio
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
import websockets
from gi.repository import GLib

logger = logging.getLogger("PartVault.SDKClient")

# Event types that trigger high-frequency token/text delta buffering
STREAM_EVENT_TYPES: Set[str] = {
    "stream_delta",
    "token_stream",
    "console_chunk",
    "agent_delta",
}


@dataclass
class WSEvent:
    event_type: str
    task_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


class CharonSDKClient:
    """
    Standalone Async Client Adapter for GTK4 with Streaming Delta Aggregation.
    Communicates with charond via HTTP REST and WebSocket streams without requiring
    the charon python package as a local dependency.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        flush_interval_sec: float = 0.033,  # ~30 FPS UI render rate
    ):
        self.client_id = client_id or f"partvault_{uuid.uuid4().hex[:8]}"
        self.base_url = (
            base_url or os.getenv("CHARON_HOST", "http://localhost:8000")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("CHARON_API_KEY", "sk_charon_dev_key")
        self.flush_interval_sec = flush_interval_sec

        ws_base = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = (
            f"{ws_base}/v1/ws?client_id={self.client_id}&api_key={self.api_key}"
        )

        # Asyncio Thread Setup
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._stop_event = asyncio.Event()

        # Callbacks mapped by event_type
        self._ui_handlers: Dict[str, list] = {}
        self._telemetry_listeners: List[Callable[[dict], None]] = []

        # Streaming Buffer State: { task_id: {"delta": accumulated_str, "metadata": dict} }
        self._stream_buffers: Dict[str, Dict[str, Any]] = {}

        # Start loop, WebSocket listener, and buffer flusher
        self._thread.start()
        self._schedule(self._websocket_listener_loop())
        self._schedule(self._stream_flusher_loop())

    @property
    def headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    def _run_async_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _schedule(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # =========================================================================
    # WEBSOCKET EVENT LISTENER & RING BUFFER FLUSHER
    # =========================================================================

    async def _websocket_listener_loop(self):
        """Persistent WebSocket connection loop with automatic reconnect & UI status events."""
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(
                    self.ws_url,
                    additional_headers={"x-api-key": self.api_key},
                ) as ws:
                    logger.info("Connected to Charon WebSocket gateway.")

                    # Signal UI that connection is active
                    self._dispatch_to_gtk(
                        "connection_status",
                        WSEvent(
                            "connection_status",
                            data={"connected": True, "url": self.ws_url},
                        ),
                    )

                    while not self._stop_event.is_set():
                        raw_msg = await ws.recv()
                        payload = json.loads(raw_msg)

                        event_type = (
                            payload.get("event")
                            or payload.get("event_type")
                            or "unknown"
                        )
                        task_id = payload.get("task_id")
                        data = payload.get("data", {})

                        # Dispatch raw telemetry event to registered listeners
                        telemetry_payload = (
                            dict(data) if isinstance(data, dict) else {"raw": data}
                        )
                        telemetry_payload["event"] = event_type
                        if task_id:
                            telemetry_payload["task_id"] = task_id

                        self._dispatch_telemetry(telemetry_payload)

                        if event_type in STREAM_EVENT_TYPES:
                            self._enqueue_stream_delta(task_id, data)
                        else:
                            if task_id and task_id in self._stream_buffers:
                                self._flush_task_buffer(task_id)

                            event = WSEvent(
                                event_type=event_type,
                                task_id=task_id,
                                data=data,
                            )
                            self._dispatch_to_gtk(event.event_type, event)

            except asyncio.CancelledError:
                break
            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    f"WebSocket disconnected ({e}). Reconnecting in 3s..."
                )

                self._dispatch_to_gtk(
                    "connection_status",
                    WSEvent(
                        "connection_status",
                        data={"connected": False, "error": str(e)},
                    ),
                )
                await asyncio.sleep(3)
            except Exception as e:
                if self._stop_event.is_set():
                    break
                logger.error(f"Unexpected WebSocket error: {e}")
                self._dispatch_to_gtk(
                    "connection_status",
                    WSEvent(
                        "connection_status",
                        data={"connected": False, "error": str(e)},
                    ),
                )
                await asyncio.sleep(3)

    def _enqueue_stream_delta(self, task_id: Optional[str], data: Dict[str, Any]):
        """Buffers rapid token/text deltas in memory on the async loop thread."""
        key = task_id or "default"
        delta_chunk = data.get("delta", "")

        if key not in self._stream_buffers:
            self._stream_buffers[key] = {"delta": delta_chunk, "data": data}
        else:
            self._stream_buffers[key]["delta"] += delta_chunk
            self._stream_buffers[key]["data"].update(data)

    async def _stream_flusher_loop(self):
        """Periodically flushes accumulated text deltas to GTK main loop."""
        while not self._stop_event.is_set():
            await asyncio.sleep(self.flush_interval_sec)
            self.flush_all_buffers()

    def flush_all_buffers(self):
        """Flushes all queued stream buffers to GTK callbacks."""
        if not self._stream_buffers:
            return

        task_keys = list(self._stream_buffers.keys())
        for task_id in task_keys:
            self._flush_task_buffer(task_id)

    def _flush_task_buffer(self, task_id: str):
        buf = self._stream_buffers.pop(task_id, None)
        if not buf or not buf["delta"]:
            return

        merged_data = dict(buf["data"])
        merged_data["delta"] = buf["delta"]

        event = WSEvent(
            event_type="stream_delta",
            task_id=None if task_id == "default" else task_id,
            data=merged_data,
        )
        self._dispatch_to_gtk("stream_delta", event)

    # =========================================================================
    # EVENT REGISTRATION & TELEMETRY DISPATCH
    # =========================================================================

    def register_ui_callback(
        self, event_type: str, callback: Callable[[WSEvent], None]
    ):
        """Registers a handler function to run safely on the GTK main thread."""
        self._ui_handlers.setdefault(event_type, []).append(callback)

    def register_telemetry_listener(self, listener: Callable[[dict], None]):
        """Registers a telemetry listener callback for raw WebSocket event dicts."""
        if listener not in self._telemetry_listeners:
            self._telemetry_listeners.append(listener)

    def _dispatch_to_gtk(self, event_type: str, event: WSEvent):
        """Dispatches incoming events safely to GTK via GLib.idle_add."""
        handlers = self._ui_handlers.get(event_type, []) + self._ui_handlers.get(
            "*", []
        )
        for handler in handlers:
            GLib.idle_add(handler, event)

    def _dispatch_telemetry(self, telemetry_data: dict):
        """Dispatches raw telemetry dictionaries to registered listeners on the GTK loop."""
        for listener in self._telemetry_listeners:
            GLib.idle_add(listener, telemetry_data)

    # =========================================================================
    # PUBLIC REST API METHODS & SYNC HOOKS
    # =========================================================================

    def sync_database(self) -> bool:
        """
        Synchronous HTTP POST request to trigger an immediate database resync in charond.
        Intended to be invoked off the GTK main thread (e.g. from HeaderBar force sync thread).
        """
        try:
            with httpx.Client(headers=self.headers, timeout=30.0) as client:
                resp = client.post(f"{self.base_url}/v1/sync")
                if resp.status_code in (200, 202):
                    logger.info("Database sync successfully triggered on charond.")
                    return True
                else:
                    logger.error(
                        f"Charon sync request failed [HTTP {resp.status_code}]: {resp.text}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to communicate with Charon sync endpoint: {e}")
            return False

    def trigger_sync(self) -> bool:
        """Alias for sync_database() for interface compatibility."""
        return self.sync_database()

    def submit_task_async(
        self,
        prompt: str,
        callback: Optional[Callable[[bool, Any], None]] = None,
        context: Optional[Dict[str, Any]] = None,
        agent_override: Optional[str] = None,
    ):
        """Submits a new task to /v1/task via HTTP REST."""

        async def _worker():
            try:
                async with httpx.AsyncClient(
                    headers=self.headers, timeout=15.0
                ) as client:
                    payload = {
                        "prompt": prompt,
                        "client_id": self.client_id,
                        "agent_override": agent_override,
                        "context": context,
                    }
                    resp = await client.post(
                        f"{self.base_url}/v1/task", json=payload
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        if callback:
                            GLib.idle_add(callback, True, data)
                    else:
                        if callback:
                            GLib.idle_add(
                                callback,
                                False,
                                f"HTTP {resp.status_code}: {resp.text}",
                            )
            except Exception as e:
                logger.error(f"Failed to submit task: {e}")
                if callback:
                    GLib.idle_add(callback, False, str(e))

        self._schedule(_worker())

    def respond_gatekeeper_async(
        self,
        approval_id: str,
        decision: str,
        notes: Optional[str] = None,
        callback: Optional[Callable[[bool, Any], None]] = None,
    ):
        """Posts human authorization to /v1/gatekeeper/respond."""

        async def _worker():
            try:
                async with httpx.AsyncClient(
                    headers=self.headers, timeout=10.0
                ) as client:
                    payload = {
                        "approval_id": approval_id,
                        "decision": decision,
                        "notes": notes,
                        "client_id": self.client_id,
                    }
                    resp = await client.post(
                        f"{self.base_url}/v1/gatekeeper/respond", json=payload
                    )
                    if callback:
                        GLib.idle_add(
                            callback, resp.status_code == 200, resp.text
                        )
            except Exception as e:
                logger.error(f"Gatekeeper response failed: {e}")
                if callback:
                    GLib.idle_add(callback, False, str(e))

        self._schedule(_worker())

    def shutdown(self):
        """Stops WebSocket connections and shuts down loop thread cleanly."""

        async def _stop():
            self._stop_event.set()
            self.flush_all_buffers()
            tasks = [
                t
                for t in asyncio.all_tasks(self._loop)
                if t is not asyncio.current_task()
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._loop.stop()

        if self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_stop(), self._loop)
            try:
                future.result(timeout=2.0)
            except Exception:
                pass

        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/dialogs/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/dialogs/edit_dialog.py`

```python
"""
partvault/ui/dialogs/edit_dialog.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Libadwaita edit modal dialog for modifying existing PartModel records.
"""

import logging
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from partvault.models.part import PartModel
from partvault.db import InventoryDatabase

logger = logging.getLogger("PartVault.EditDialog")


class EditPartDialog:
    """
    Controller for editing an existing component using an Adw.MessageDialog layout.
    """

    def __init__(
        self,
        parent_window: Gtk.Window,
        part: PartModel,
        db: InventoryDatabase,
        on_saved_callback: Optional[Callable[[PartModel], None]] = None,
    ):
        self.parent_window = parent_window
        self.part = part
        self.db = db
        self.on_saved_callback = on_saved_callback

        self._build_dialog()

    def _build_dialog(self):
        self.dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading=f"Edit {self.part.mpn}",
            body="Modify component details and stock levels.",
        )

        group = Adw.PreferencesGroup()

        # Input Rows pre-filled with current part details
        self.entry_mfr = Adw.EntryRow(title="Manufacturer")
        self.entry_mfr.set_text(self.part.manufacturer or "")

        self.entry_desc = Adw.EntryRow(title="Description")
        self.entry_desc.set_text(self.part.description or "")

        self.entry_category = Adw.EntryRow(title="Category")
        self.entry_category.set_text(self.part.category or "General")

        self.entry_footprint = Adw.EntryRow(title="Package / Footprint")
        self.entry_footprint.set_text(self.part.package_footprint or "")

        self.entry_bin = Adw.EntryRow(title="Bin Location")
        self.entry_bin.set_text(self.part.bin_location or "Unassigned")

        self.entry_qty = Adw.EntryRow(title="Quantity")
        self.entry_qty.set_text(str(self.part.quantity))

        group.add(self.entry_mfr)
        group.add(self.entry_desc)
        group.add(self.entry_category)
        group.add(self.entry_footprint)
        group.add(self.entry_bin)
        group.add(self.entry_qty)

        self.dialog.set_extra_child(group)

        # Dialog Actions
        self.dialog.add_response("cancel", "Cancel")
        self.dialog.add_response("save", "Save Changes")
        self.dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        self.dialog.connect("response", self._on_response)

    def _on_response(self, dialog: Adw.MessageDialog, response: str):
        if response == "save":
            try:
                new_qty = int(self.entry_qty.get_text().strip() or "0")
            except ValueError:
                new_qty = self.part.quantity

            # Update Model fields
            self.part.manufacturer = self.entry_mfr.get_text().strip()
            self.part.description = self.entry_desc.get_text().strip()
            self.part.category = self.entry_category.get_text().strip() or "General"
            self.part.package_footprint = self.entry_footprint.get_text().strip()
            self.part.bin_location = self.entry_bin.get_text().strip() or "Unassigned"
            self.part.quantity = new_qty

            # Persist changes to DB
            if self.db.upsert_part(self.part):
                logger.info(f"Updated component metadata for '{self.part.mpn}'")
                if self.on_saved_callback:
                    self.on_saved_callback(self.part)
            else:
                logger.error(f"Failed to save changes for '{self.part.mpn}'")

    def present(self):
        """Displays the modal dialog."""
        self.dialog.present()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/headerbar.py`

```python
"""
partvault/ui/headerbar.py
System Version: v0.1.0 | File Revision: 1.3.0

Module: HeaderBar controller for PartVault using GTK4 & Libadwaita.
Encapsulates Adw.HeaderBar (a final GObject class in Libadwaita).
"""

import logging
import threading
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gio, Gtk

from partvault.db import InventoryDatabase

logger = logging.getLogger("PartVault.HeaderBar")


class PartVaultHeaderBar:
    """
    Controller/wrapper for Adw.HeaderBar providing title controls, sync status,
    force-sync button, add component button, primary menu, and Charon console toggle.

    Note: Adw.HeaderBar is a final GType in Libadwaita and cannot be subclassed directly.
    """

    def __init__(
        self,
        db: InventoryDatabase,
        sync_callback: Callable[[], bool],
        on_add_part_clicked: Callable[[Gtk.Button], None],
        on_console_toggled: Callable[[Gtk.ToggleButton], None],
        primary_menu: Optional[Gio.Menu] = None,
    ):
        self.db = db
        self.sync_callback = sync_callback
        self.on_add_part_clicked = on_add_part_clicked
        self.on_console_toggled = on_console_toggled

        # Instantiate the underlying Adw.HeaderBar instance
        self.widget = Adw.HeaderBar()

        self._build_ui(primary_menu)
        self.refresh_sync_status()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self, primary_menu: Optional[Gio.Menu]):
        # 1. Add Component Button (Start)
        self.add_button = Gtk.Button(
            icon_name="list-add-symbolic",
            tooltip_text="Ingest New Component",
        )
        self.add_button.connect("clicked", self.on_add_part_clicked)
        self.widget.pack_start(self.add_button)

        # 2. Sync Status Container (Start)
        sync_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.sync_icon = Gtk.Image(icon_name="emblem-ok-symbolic")
        self.sync_label = Gtk.Label(label="Synced")
        self.sync_label.add_css_class("caption")
        self.sync_label.add_css_class("dim-label")

        self.force_sync_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Force Sync Database",
        )
        self.force_sync_btn.add_css_class("flat")
        self.force_sync_btn.connect("clicked", self._on_force_sync_clicked)

        sync_box.append(self.sync_icon)
        sync_box.append(self.sync_label)
        sync_box.append(self.force_sync_btn)
        self.widget.pack_start(sync_box)

        # 3. Title Widget (Center)
        title_widget = Adw.WindowTitle(
            title="PartVault",
            subtitle="Electronic Component Catalog",
        )
        self.widget.set_title_widget(title_widget)

        # 4. Console Toggle Button (End)
        self.console_toggle_btn = Gtk.ToggleButton(
            icon_name="utilities-terminal-symbolic",
            tooltip_text="Toggle Charon Assistant Console",
        )
        self.console_toggle_btn.connect("toggled", self.on_console_toggled)
        self.widget.pack_end(self.console_toggle_btn)

        # 5. Primary Menu Button (End)
        if primary_menu:
            self.menu_button = Gtk.MenuButton(
                icon_name="open-menu-symbolic",
                menu_model=primary_menu,
                tooltip_text="Main Menu",
            )
            self.widget.pack_end(self.menu_button)

    # =========================================================================
    # SYNC ACTIONS & STATE MANAGEMENT
    # =========================================================================

    def _on_force_sync_clicked(self, button: Gtk.Button):
        """Triggers the manual re-sync in a background thread."""
        self.set_sync_state("syncing", "Syncing...")
        self.force_sync_btn.set_sensitive(False)

        def worker():
            try:
                success = self.sync_callback()
                GLib.idle_add(self._on_sync_complete, success)
            except Exception as e:
                logger.error(f"Force sync thread error: {e}")
                GLib.idle_add(self._on_sync_complete, False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_sync_complete(self, success: bool):
        self.force_sync_btn.set_sensitive(True)
        if success:
            self.set_sync_state("synced", "Synced")
        else:
            self.set_sync_state("error", "Sync Failed")

    def refresh_sync_status(self):
        """Queries local database metadata to reflect synchronization state."""
        try:
            meta = (
                self.db.get_sync_metadata()
                if hasattr(self.db, "get_sync_metadata")
                else {}
            )
            is_dirty = meta.get("dirty", False)
            if is_dirty:
                self.set_sync_state("dirty", "Unsaved Changes")
            else:
                self.set_sync_state("synced", "Synced")
        except Exception as e:
            logger.warning(f"Could not read sync status metadata: {e}")
            self.set_sync_state("synced", "Synced")

    def set_sync_state(self, state: str, message: str):
        """Updates header bar UI widgets to match current sync state."""
        self.sync_label.set_text(message)

        if state == "syncing":
            self.sync_icon.set_from_icon_name("emblem-synchronizing-symbolic")
        elif state == "dirty":
            self.sync_icon.set_from_icon_name("emblem-important-symbolic")
        elif state == "error":
            self.sync_icon.set_from_icon_name("dialog-error-symbolic")
        else:  # synced
            self.sync_icon.set_from_icon_name("emblem-ok-symbolic")

    def on_telemetry_event(self, event_data: dict):
        """Responds to push events broadcast from Charon's WebSocket server."""
        event_type = event_data.get("event")
        if event_type == "sync_started":
            self.set_sync_state("syncing", "Syncing...")
        elif event_type in ("sync_completed", "database_synced"):
            self.set_sync_state("synced", "Synced")
        elif event_type == "sync_failed":
            self.set_sync_state("error", "Sync Error")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/views/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/views/console_view.py`

```python
import logging
from typing import Any, Dict, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Pango

from partvault.services.charon_client import CharonSDKClient, WSEvent

logger = logging.getLogger("PartVault.ConsoleView")


class CharonConsoleView(Gtk.Box):
    """
    Interactive Assistant Drawer & Log Console.
    Communicates asynchronously with charond over HTTP REST and WebSocket streams,
    supporting real-time delta rendering and interactive Gatekeeper intercepts.
    """

    def __init__(self, sdk_client: Optional[CharonSDKClient] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.sdk_client = sdk_client or CharonSDKClient()
        self._current_approval_id: Optional[str] = None

        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self._build_ui()
        self._setup_text_tags()
        self._register_sdk_listeners()

        self._append_system_msg("The Continental Assistant initialized.")

    def _build_ui(self):
        # Header Bar
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        title_label = Gtk.Label(label="The Continental Assistant", xalign=0)
        title_label.add_css_class("title-3")
        title_label.set_hexpand(True)
        header_box.append(title_label)

        # Connection Status Badge Indicator
        self.status_badge = Gtk.Label(label="Connecting...")
        self.status_badge.add_css_class("pill")
        self.status_badge.add_css_class("dim-label")
        header_box.append(self.status_badge)

        clear_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        clear_btn.set_tooltip_text("Clear Log Window")
        clear_btn.connect("clicked", self._on_clear_log)
        header_box.append(clear_btn)

        self.append(header_box)

        # Text View Log Display
        self.text_view = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            pixels_above_lines=3,
            pixels_below_lines=3,
        )
        self.text_view.add_css_class("monospace")
        self.buffer = self.text_view.get_buffer()

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_vexpand(True)
        log_scroll.set_child(self.text_view)
        self.append(log_scroll)

        # Dynamic Gatekeeper Approval Banner
        self.gatekeeper_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.gatekeeper_box.add_css_class("card")
        self.gatekeeper_box.set_margin_top(4)
        self.gatekeeper_box.set_margin_bottom(4)
        self.gatekeeper_box.set_visible(False)

        self.gatekeeper_label = Gtk.Label(
            label="Gatekeeper Intercept: Action requires authorization.",
            hexpand=True,
            xalign=0,
            wrap=True,
        )
        self.gatekeeper_box.append(self.gatekeeper_label)

        self.approve_btn = Gtk.Button(label="Proceed")
        self.approve_btn.add_css_class("suggested-action")
        self.approve_btn.connect("clicked", self._on_gatekeeper_decision, "proceed")
        self.gatekeeper_box.append(self.approve_btn)

        self.deny_btn = Gtk.Button(label="Cancel")
        self.deny_btn.add_css_class("destructive-action")
        self.deny_btn.connect("clicked", self._on_gatekeeper_decision, "cancel")
        self.gatekeeper_box.append(self.deny_btn)

        self.append(self.gatekeeper_box)

        # Prompt Entry & Send Bar
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.prompt_entry = Gtk.Entry(
            placeholder_text="Ask Charon (e.g., 'Audit inventory for MCU-01')..."
        )
        self.prompt_entry.set_hexpand(True)
        self.prompt_entry.connect("activate", self._on_send_clicked)
        input_box.append(self.prompt_entry)

        self.spinner = Gtk.Spinner()
        input_box.append(self.spinner)

        self.send_btn = Gtk.Button(icon_name="paper-plane-symbolic")
        self.send_btn.set_tooltip_text("Transmit Prompt")
        self.send_btn.connect("clicked", self._on_send_clicked)
        input_box.append(self.send_btn)

        self.append(input_box)

    def _setup_text_tags(self):
        self.tag_user = self.buffer.create_tag(
            "user", weight=Pango.Weight.BOLD, pixels_above_lines=6
        )
        self.tag_charon = self.buffer.create_tag(
            "charon", pixels_below_lines=4
        )
        self.tag_system = self.buffer.create_tag(
            "system", style=Pango.Style.ITALIC, scale=0.9
        )
        self.tag_error = self.buffer.create_tag(
            "error", weight=Pango.Weight.BOLD
        )

    def _register_sdk_listeners(self):
        """Registers direct callbacks with CharonSDKClient."""
        self.sdk_client.register_ui_callback("connection_status", self._on_connection_status_changed)
        self.sdk_client.register_ui_callback("stream_delta", self._on_stream_chunk)
        self.sdk_client.register_ui_callback("task_stream", self._on_stream_chunk)
        self.sdk_client.register_ui_callback("agent_log", self._on_stream_chunk)
        self.sdk_client.register_ui_callback("gatekeeper_intercept", self._on_gatekeeper_intercept)
        self.sdk_client.register_ui_callback("concierge_suggestion", self._on_concierge_suggestion)
        self.sdk_client.register_ui_callback("system_alert", self._on_system_alert)
        self.sdk_client.register_ui_callback("task_complete", self._on_task_completed)
        self.sdk_client.register_ui_callback("task_error", self._on_task_error)

    # =========================================================================
    # WEBSOCKET EVENT DISPATCHERS
    # =========================================================================

    def _on_connection_status_changed(self, event: WSEvent):
        connected = event.data.get("connected", False)

        self.status_badge.remove_css_class("success")
        self.status_badge.remove_css_class("error")
        self.status_badge.remove_css_class("dim-label")

        if connected:
            self.status_badge.set_text("Online")
            self.status_badge.add_css_class("success")
            self._append_system_msg("Gateway connected.")
        else:
            self.status_badge.set_text("Offline")
            self.status_badge.add_css_class("error")
            err_msg = event.data.get("error", "Gateway disconnected.")
            self._append_error_msg(f"Connection lost ({err_msg}). Retrying...")

    def _on_stream_chunk(self, event: WSEvent):
        chunk = event.data.get("delta") or event.data.get("message", "")
        if chunk:
            end_iter = self.buffer.get_end_iter()
            self.buffer.insert_with_tags(end_iter, chunk, self.tag_charon)
            self._scroll_to_bottom()

    def _on_gatekeeper_intercept(self, event: WSEvent):
        self.spinner.stop()
        self._current_approval_id = event.data.get("approval_id")
        action = event.data.get("action", "High-risk system action requested.")

        self.gatekeeper_label.set_text(f"🛡️ Gatekeeper Intercept: {action}")
        self.gatekeeper_box.set_visible(True)
        self._append_system_msg(f"Gatekeeper intercepted action [{action}]. Approval required.")

    def _on_gatekeeper_decision(self, button: Gtk.Button, decision: str):
        self.gatekeeper_box.set_visible(False)
        if not self._current_approval_id:
            return

        self._append_system_msg(f"Authorization response '{decision}' transmitted.")
        self.spinner.start()

        self.sdk_client.respond_gatekeeper_async(
            approval_id=self._current_approval_id,
            decision=decision,
            notes="Decision made via PartVault Assistant Drawer",
        )
        self._current_approval_id = None

    def _on_concierge_suggestion(self, event: WSEvent):
        rec = event.data.get("next_step") or event.data.get("recommendation", "")
        if rec:
            self._append_system_msg(f"💡 Concierge Suggestion: {rec}")

    def _on_system_alert(self, event: WSEvent):
        msg = event.data.get("message", "")
        if msg:
            self._append_error_msg(f"System Alert: {msg}")

    def _on_task_completed(self, event: WSEvent):
        self._unlock_ui()
        summary = event.data.get("summary", "")
        if summary and not event.data.get("streamed", True):
            self._append_text(f"\n{summary}\n", self.tag_charon)

    def _on_task_error(self, event: WSEvent):
        self._unlock_ui()
        err = event.data.get("error", "An error occurred during task execution.")
        self._append_error_msg(err)

    # =========================================================================
    # LOGGING & UI HELPERS
    # =========================================================================

    def _scroll_to_bottom(self):
        mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        self.buffer.delete_mark(mark)

    def _append_text(self, text: str, tag: Gtk.TextTag):
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert_with_tags(end_iter, text + "\n", tag)
        self._scroll_to_bottom()

    def _append_system_msg(self, text: str):
        self._append_text(f"[System]: {text}", self.tag_system)

    def _append_user_msg(self, text: str):
        self._append_text(f"\n> {text}", self.tag_user)

    def _append_error_msg(self, text: str):
        self._append_text(f"[Error]: {text}", self.tag_error)

    def _lock_ui(self):
        self.prompt_entry.set_sensitive(False)
        self.send_btn.set_sensitive(False)
        self.spinner.start()

    def _unlock_ui(self):
        self.spinner.stop()
        self.prompt_entry.set_sensitive(True)
        self.send_btn.set_sensitive(True)
        self.prompt_entry.grab_focus()

    # =========================================================================
    # PUBLIC API & USER ACTIONS
    # =========================================================================

    def _on_clear_log(self, button):
        self.buffer.set_text("")
        self._append_system_msg("Console log cleared.")

    def _on_send_clicked(self, widget):
        prompt = self.prompt_entry.get_text().strip()
        if not prompt:
            return

        self.prompt_entry.set_text("")
        self.send_prompt(prompt)

    def send_prompt(self, prompt: str, context: Optional[Dict[str, Any]] = None):
        """Public API to programmatically transmit prompts with contextual data."""
        self._append_user_msg(prompt)
        self._lock_ui()

        def _on_submit_response(success: bool, response_or_err: Any):
            if not success:
                GLib.idle_add(self._unlock_ui)
                GLib.idle_add(self._append_error_msg, f"Submission failed: {response_or_err}")

        self.sdk_client.submit_task_async(
            prompt=prompt,
            context=context,
            callback=_on_submit_response,
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/views/detail_view.py`

```python
"""
partvault/ui/views/detail_view.py
System Version: v0.1.0 | File Revision: 1.2.2

Module: Detail View Controller displaying component specs, stock controls,
StatusBadge indicators, EditPartDialog triggers, and RAG search actions.
"""

import logging
import os
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from partvault.db import InventoryDatabase
from partvault.models.part import PartModel
from partvault.ui.dialogs.edit_dialog import EditPartDialog
from partvault.ui.widgets.status_badge import StatusBadge

logger = logging.getLogger("PartVault.DetailView")


class DetailView(Gtk.ScrolledWindow):
    """
    Detail View Controller displaying specs, live status badges, stock levels,
    edit modals, and datasheet RAG actions for the currently selected PartModel.
    """

    def __init__(
        self,
        db: Optional[InventoryDatabase] = None,
        on_query_rag_callback: Optional[Callable[[str], None]] = None,
        on_quantity_changed_callback: Optional[Callable[[str, int], None]] = None,
        on_part_updated_callback: Optional[Callable[[PartModel], None]] = None,
    ):
        super().__init__()
        self.db = db or InventoryDatabase()
        self.on_query_rag_callback = on_query_rag_callback
        self.on_quantity_changed_callback = on_quantity_changed_callback
        self.on_part_updated_callback = on_part_updated_callback
        self.current_part: Optional[PartModel] = None

        # Track handler IDs for unbinding signal listeners cleanly
        self._notify_handlers = []

        self._build_ui()

    def _build_ui(self):
        self.set_vexpand(True)
        self.set_hexpand(True)

        clamp = Adw.Clamp(maximum_size=800)
        clamp.set_margin_top(16)
        clamp.set_margin_bottom(16)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        # --- Empty State Widget ---
        self.status_page = Adw.StatusPage(
            icon_name="package-x-generic-symbolic",
            title="No Part Selected",
            description="Select a part from the inventory list to view details and query specs.",
        )
        self.main_box.append(self.status_page)

        # --- Detail Content Box ---
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.content_box.set_visible(False)

        # --- Header Box (Title, Status Badge, & Edit Button) ---
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.title_label = Gtk.Label(xalign=0)
        self.title_label.add_css_class("title-1")
        self.title_label.set_hexpand(True)

        self.status_badge = StatusBadge()

        self.btn_edit = Gtk.Button(
            icon_name="document-edit-symbolic",
            tooltip_text="Edit Component Details",
        )
        self.btn_edit.add_css_class("flat")
        self.btn_edit.connect("clicked", self._on_edit_clicked)

        header_box.append(self.title_label)
        header_box.append(self.status_badge)
        header_box.append(self.btn_edit)
        self.content_box.append(header_box)

        self.desc_label = Gtk.Label(xalign=0, wrap=True)
        self.desc_label.add_css_class("dim-label")
        self.content_box.append(self.desc_label)

        # --- Group 1: Stock & Storage Location ---
        stock_group = Adw.PreferencesGroup(title="Stock &amp; Location")

        self.row_qty = Adw.ActionRow(title="Quantity on Hand")

        qty_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.btn_dec = Gtk.Button(icon_name="list-remove-symbolic")
        self.btn_dec.set_tooltip_text("Decrease Stock")
        self.btn_dec.connect("clicked", self._on_qty_decrement)

        self.qty_value_label = Gtk.Label(label="0")
        self.qty_value_label.add_css_class("title-4")
        self.qty_value_label.set_margin_start(6)
        self.qty_value_label.set_margin_end(6)

        self.btn_inc = Gtk.Button(icon_name="list-add-symbolic")
        self.btn_inc.set_tooltip_text("Increase Stock")
        self.btn_inc.connect("clicked", self._on_qty_increment)

        qty_controls.append(self.btn_dec)
        qty_controls.append(self.qty_value_label)
        qty_controls.append(self.btn_inc)

        self.row_qty.add_suffix(qty_controls)
        stock_group.add(self.row_qty)

        self.row_bin = Adw.ActionRow(title="Storage Bin")
        stock_group.add(self.row_bin)

        self.row_category = Adw.ActionRow(title="Category")
        stock_group.add(self.row_category)

        self.row_mfr = Adw.ActionRow(title="Manufacturer &amp; Footprint")
        stock_group.add(self.row_mfr)

        self.content_box.append(stock_group)

        # --- Group 2: Technical Datasheet & RAG Memory ---
        rag_group = Adw.PreferencesGroup(
            title="Archivist Knowledge Base",
            description="Query vector-embedded datasheet specs directly through Charon.",
        )

        self.row_datasheet = Adw.ActionRow(title="Datasheet Status")
        self.btn_open_ds = Gtk.Button(icon_name="document-open-symbolic")
        self.btn_open_ds.set_tooltip_text("Open Datasheet File")
        self.btn_open_ds.connect("clicked", self._on_open_datasheet)
        self.row_datasheet.add_suffix(self.btn_open_ds)
        rag_group.add(self.row_datasheet)

        self.row_rag_action = Adw.ActionRow(
            title="Query Peripheral Specs",
            subtitle="Ask Charon to search vector memory for pinouts, voltage, and features.",
        )
        btn_query = Gtk.Button(label="Query Specs")
        btn_query.add_css_class("suggested-action")
        btn_query.connect("clicked", self._on_query_specs)
        self.row_rag_action.add_suffix(btn_query)
        rag_group.add(self.row_rag_action)

        self.content_box.append(rag_group)

        self.main_box.append(self.content_box)
        clamp.set_child(self.main_box)
        self.set_child(clamp)

    # =========================================================================
    # DATA BINDING & UPDATES
    # =========================================================================

    def bind_part(self, part: Optional[PartModel]):
        """Binds a PartModel instance to the detail view fields."""
        if self.current_part and self._notify_handlers:
            for handler_id in self._notify_handlers:
                self.current_part.disconnect(handler_id)
            self._notify_handlers.clear()

        self.current_part = part

        if not part:
            self.status_page.set_visible(True)
            self.content_box.set_visible(False)
            return

        self.status_page.set_visible(False)
        self.content_box.set_visible(True)

        self._update_fields()

        h1 = part.connect("notify::quantity", lambda *_: self._update_fields())
        h2 = part.connect("notify::bin-location", lambda *_: self._update_fields())
        self._notify_handlers.extend([h1, h2])

    def _update_fields(self):
        """Refreshes text labels and status badges based on PartModel state."""
        if not self.current_part:
            return

        part = self.current_part
        self.title_label.set_text(part.mpn)
        self.desc_label.set_text(part.description or "No description provided.")

        # Update Live Status Badge
        threshold = getattr(part, "min_threshold", 5)
        self.status_badge.set_stock_level(part.quantity, threshold)

        self.qty_value_label.set_text(str(part.quantity))
        self.row_qty.set_subtitle(f"Minimum threshold: {threshold} units")

        self.row_bin.set_subtitle(part.bin_location or "Unassigned")

        cat_text = part.category or "General"
        if part.sub_category:
            cat_text += f" / {part.sub_category}"
        self.row_category.set_subtitle(cat_text)

        mfr_text = part.manufacturer or "Generic"
        if part.package_footprint:
            mfr_text += f" ({part.package_footprint})"
        self.row_mfr.set_subtitle(mfr_text)

        # Validate path on disk for datasheet button sensitivity
        if part.datasheet_path and os.path.exists(part.datasheet_path):
            self.row_datasheet.set_subtitle(f"Indexed: {part.datasheet_path}")
            self.btn_open_ds.set_sensitive(True)
        elif part.datasheet_path:
            self.row_datasheet.set_subtitle(f"File missing: {part.datasheet_path}")
            self.btn_open_ds.set_sensitive(False)
        else:
            self.row_datasheet.set_subtitle("No datasheet linked")
            self.btn_open_ds.set_sensitive(False)

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_edit_clicked(self, button: Gtk.Button):
        """Displays the EditPartDialog modal for modifying current component fields."""
        if not self.current_part:
            return

        root_win = self.get_native()
        parent = root_win if isinstance(root_win, Gtk.Window) else None

        dialog = EditPartDialog(
            parent_window=parent,
            part=self.current_part,
            db=self.db,
            on_saved_callback=self._on_part_edited,
        )
        dialog.present()

    def _on_part_edited(self, updated_part: PartModel):
        """Callback invoked when edits are persisted via EditPartDialog."""
        self._update_fields()
        if self.on_part_updated_callback:
            self.on_part_updated_callback(updated_part)

    def _on_qty_increment(self, button):
        if self.current_part:
            self.current_part.quantity += 1
            if self.on_quantity_changed_callback:
                self.on_quantity_changed_callback(
                    self.current_part.mpn, self.current_part.quantity
                )

    def _on_qty_decrement(self, button):
        if self.current_part and self.current_part.quantity > 0:
            self.current_part.quantity -= 1
            if self.on_quantity_changed_callback:
                self.on_quantity_changed_callback(
                    self.current_part.mpn, self.current_part.quantity
                )

    def _on_open_datasheet(self, button: Gtk.Button):
        """Launches the datasheet PDF/file in the OS default viewer application."""
        if not self.current_part or not self.current_part.datasheet_path:
            return

        ds_path = self.current_part.datasheet_path
        if not os.path.exists(ds_path):
            logger.error(f"Cannot launch datasheet — file does not exist: {ds_path}")
            self._update_fields()
            return

        gfile = Gio.File.new_for_path(ds_path)

        # Use GTK4 Gtk.FileLauncher if available, fallback to Gio default handler
        if hasattr(Gtk, "FileLauncher"):
            launcher = Gtk.FileLauncher.new(gfile)
            root_win = self.get_native()
            parent = root_win if isinstance(root_win, Gtk.Window) else None
            launcher.launch(parent, None, self._on_datasheet_launched)
        else:
            gfile.launch_default_handler_async(None, None, self._on_datasheet_launched_gio)

    def _on_datasheet_launched(self, launcher: Gtk.FileLauncher, result: Gio.AsyncResult):
        try:
            launcher.launch_finish(result)
            logger.info("Datasheet opened successfully in default viewer.")
        except Exception as e:
            logger.error(f"Failed to launch default datasheet viewer: {e}")

    def _on_datasheet_launched_gio(self, gfile: Gio.File, result: Gio.AsyncResult):
        try:
            gfile.launch_default_handler_finish(result)
            logger.info("Datasheet opened successfully via Gio handler.")
        except Exception as e:
            logger.error(f"Failed to launch default datasheet viewer via Gio: {e}")

    def _on_query_specs(self, button: Gtk.Button):
        if not self.current_part:
            return

        prompt = f"What are the core specs, pinout features, and peripherals for {self.current_part.mpn}?"
        if self.on_query_rag_callback:
            self.on_query_rag_callback(prompt)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/views/inventory_view.py`

```python
"""
partvault/views/inventory_view.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: ListView controller for browsing, filtering, and selecting stock inventory.
"""

import logging
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GObject, Gtk

logger = logging.getLogger("PartVault.InventoryView")


class InventoryView(Gtk.Box):
    """
    Controller widget for browsing, filtering, and selecting inventory parts.
    Uses Gtk.ListView + Gtk.FilterListModel for high-performance virtualized rendering.
    """

    def __init__(self, on_part_selected_callback: Optional[Callable] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.on_part_selected_callback = on_part_selected_callback

        # 1. Underlying GObject Data Store & Filtering
        self.store = Gio.ListStore(item_type=GObject.Object)
        self.filter = Gtk.CustomFilter.new(self._filter_func)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self.filter)

        # 2. Selection Model
        self.selection_model = Gtk.SingleSelection(model=self.filter_model)
        self.selection_model.connect("selection-changed", self._on_selection_changed)

        self._build_ui()

    def _build_ui(self):
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        # --- Search Bar ---
        self.search_entry = Gtk.SearchEntry(
            placeholder_text="Search MPN, Bin, Category, or Description..."
        )
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.append(self.search_entry)

        # --- Factory for Row Widgets ---
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)

        # --- Virtualized ListView ---
        self.list_view = Gtk.ListView(
            model=self.selection_model, factory=factory
        )
        self.list_view.add_css_class("navigation-sidebar")

        # Scrollable container
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.list_view)
        self.append(scroll)

    # =========================================================================
    # FACTORY BINDINGS
    # =========================================================================

    def _on_factory_setup(self, factory, list_item):
        """Instantiates row widgets as lightweight native containers."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)

        title_label = Gtk.Label(xalign=0)
        title_label.add_css_class("heading")

        subtitle_label = Gtk.Label(xalign=0)
        subtitle_label.add_css_class("caption")
        subtitle_label.add_css_class("dim-label")

        vbox.append(title_label)
        vbox.append(subtitle_label)

        qty_label = Gtk.Label()
        qty_label.add_css_class("pill")
        qty_label.set_valign(Gtk.Align.CENTER)

        box.append(vbox)
        box.append(qty_label)

        box._title_label = title_label
        box._subtitle_label = subtitle_label
        box._qty_label = qty_label

        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        """Binds GObject model properties to row UI elements."""
        item = list_item.get_item()
        box = list_item.get_child()

        if item and box:
            mpn = getattr(item, "mpn", "Unknown MPN")
            mfr = getattr(item, "manufacturer", "")
            title_text = f"{mfr} {mpn}".strip() if mfr else mpn
            box._title_label.set_text(title_text)

            category = getattr(item, "category", "General")
            sub_cat = getattr(item, "sub_category", "")
            bin_loc = getattr(item, "bin_location", "Unassigned")

            cat_display = f"{category}/{sub_cat}" if sub_cat else category
            box._subtitle_label.set_text(f"{cat_display} • Bin: {bin_loc}")

            qty = getattr(item, "quantity", 0)
            box._qty_label.set_text(f"{qty} in stock")

            box._qty_label.remove_css_class("error")
            box._qty_label.remove_css_class("success")
            min_thresh = getattr(item, "min_threshold", 2)
            if qty <= min_thresh:
                box._qty_label.add_css_class("error")
            else:
                box._qty_label.add_css_class("success")

    # =========================================================================
    # FILTERING & SELECTION HANDLERS
    # =========================================================================

    def _filter_func(self, item) -> bool:
        """Predicate checking if an item matches the active search query."""
        query = self.search_entry.get_text().strip().lower()
        if not query:
            return True

        mpn = getattr(item, "mpn", "").lower()
        mfr = getattr(item, "manufacturer", "").lower()
        desc = getattr(item, "description", "").lower()
        bin_loc = getattr(item, "bin_location", "").lower()
        category = getattr(item, "category", "").lower()

        return (
            (query in mpn)
            or (query in mfr)
            or (query in desc)
            or (query in bin_loc)
            or (query in category)
        )

    def _on_search_changed(self, entry):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_selection_changed(self, selection, position, n_items):
        selected_item = selection.get_selected_item()
        if selected_item and self.on_part_selected_callback:
            self.on_part_selected_callback(selected_item)

    # =========================================================================
    # PUBLIC DATA API
    # =========================================================================

    def populate(self, part_list: list):
        """Populates the list model with a list of PartModel GObjects."""
        self.store.remove_all()
        for part in part_list:
            self.store.append(part)

    def add_part(self, part):
        """Appends a new PartModel GObject to the list."""
        self.store.append(part)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/widgets/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/widgets/status_badge.py`

```python
"""
partvault/ui/widgets/status_badge.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Reusable GTK4/Libadwaita status badge widget for stock indicators
and category tagging.
"""

from enum import Enum
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class BadgeStyle(Enum):
    NEUTRAL = "dim-label"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ACCENT = "accent"


class StatusBadge(Gtk.Box):
    """
    Custom GTK4 pill/badge widget for displaying component stock levels,
    sync states, or category labels.
    """

    def __init__(
            self,
            text: str = "",
            style: BadgeStyle = BadgeStyle.NEUTRAL,
            icon_name: str = "",
            **kwargs
    ):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, **kwargs)
        self.add_css_class("badge-box")

        # Apply padding and rounded pill layout
        self.set_margin_top(2)
        self.set_margin_bottom(2)
        self.set_margin_start(4)
        self.set_margin_end(4)

        # Icon
        self.icon = Gtk.Image()
        self.append(self.icon)

        # Label
        self.label = Gtk.Label()
        self.label.add_css_class("caption")
        self.label.add_css_class("bold")
        self.append(self.label)

        self._current_style_class: str = ""
        self.set_badge(text, style, icon_name)

    def set_badge(self, text: str, style: BadgeStyle = BadgeStyle.NEUTRAL, icon_name: str = ""):
        """Updates text, icon, and visual styling class of the badge."""
        self.label.set_text(text)

        # Icon visibility
        if icon_name:
            self.icon.set_from_icon_name(icon_name)
            self.icon.set_visible(True)
        else:
            self.icon.set_visible(False)

        # Remove previous styling class
        if self._current_style_class:
            self.remove_css_class(self._current_style_class)
            self.label.remove_css_class(self._current_style_class)

        # Apply new styling class
        if style != BadgeStyle.NEUTRAL:
            self._current_style_class = style.value
            self.add_css_class(self._current_style_class)
            self.label.add_css_class(self._current_style_class)

    def set_stock_level(self, quantity: int, low_threshold: int = 5):
        """Helper to quickly set badge status based on numerical inventory count."""
        if quantity <= 0:
            self.set_badge("Out of Stock", BadgeStyle.ERROR, "dialog-error-symbolic")
        elif quantity <= low_threshold:
            self.set_badge(f"Low Stock ({quantity})", BadgeStyle.WARNING, "dialog-warning-symbolic")
        else:
            self.set_badge(f"In Stock ({quantity})", BadgeStyle.SUCCESS, "emblem-ok-symbolic")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/partvault/ui/window.py`

```python
"""
partvault/ui/window.py
System Version: v0.1.0 | File Revision: 1.3.0

Module: Main Application Controller for PartVault using GTK4 & Libadwaita.
Integrates InventoryDatabase, Charon SDK Gateway, real-time sync status header,
and navigation drawer views.
"""

import logging
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gio, Gtk

from partvault.db import InventoryDatabase
from partvault.models.part import PartModel
from partvault.services.charon_client import CharonSDKClient
from partvault.ui.headerbar import PartVaultHeaderBar
from partvault.ui.views.console_view import CharonConsoleView
from partvault.ui.views.detail_view import DetailView
from partvault.ui.views.inventory_view import InventoryView

logger = logging.getLogger("PartVault.Window")


class PartVaultWindow(Adw.ApplicationWindow):
    """Main Application Controller for PartVault, integrated with Charon SDK Gateway."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("PartVault")
        self.set_default_size(1150, 720)

        # 1. Initialize DB and SDK Client
        self.db = InventoryDatabase()
        self.sdk_client = CharonSDKClient(client_id="partvault-app")

        # Register telemetry listener for real-time WebSocket push updates
        if hasattr(self.sdk_client, "register_telemetry_listener"):
            self.sdk_client.register_telemetry_listener(self._on_telemetry_event)

        self._active_part: Optional[PartModel] = None
        self._qty_notify_handler_id = 0

        # 2. Register Actions & Keyboard Shortcuts
        self._setup_actions()

        # 3. Build Component Views & Wire Layout
        self._build_ui()

        # 4. Load initial database records into UI
        self.refresh_inventory()

    # =========================================================================
    # ACTIONS & MENUS SETUP
    # =========================================================================

    def _setup_actions(self):
        """Registers window-level Gio SimpleActions."""
        actions = [
            ("refresh", self._on_refresh_action),
            ("preferences", self._on_preferences_action),
            ("about", self._on_about_action),
        ]

        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _create_primary_menu(self) -> Gio.Menu:
        """Constructs the canonical GNOME primary menu model."""
        menu = Gio.Menu()

        # Section 1: Inventory Actions
        section_inventory = Gio.Menu()
        section_inventory.append("Refresh Inventory", "win.refresh")
        menu.append_section(None, section_inventory)

        # Section 2: Configuration & Tools
        section_tools = Gio.Menu()
        section_tools.append("Preferences", "win.preferences")
        menu.append_section(None, section_tools)

        # Section 3: App Information
        section_about = Gio.Menu()
        section_about.append("About PartVault", "win.about")
        menu.append_section(None, section_about)

        return menu

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # --- Top Header Bar with Sync Status & Force Sync Control ---
        self.header_bar = PartVaultHeaderBar(
            db=self.db,
            sync_callback=self._on_force_sync,
            on_add_part_clicked=self._on_add_part_dialog,
            on_console_toggled=self._on_console_toggled,
            primary_menu=self._create_primary_menu(),
        )
        # Pass the inner Adw.HeaderBar Gtk widget instance to Adw.ToolbarView
        self.toolbar_view.add_top_bar(self.header_bar.widget)

        # --- Layout Containers ---
        self.console_split = Adw.OverlaySplitView()
        self.console_split.set_sidebar_position(Gtk.PackType.END)
        self.console_split.set_collapsed(True)
        self.toolbar_view.set_content(self.console_split)

        self.nav_split = Adw.NavigationSplitView()
        self.console_split.set_content(self.nav_split)

        # Inventory View Widget (Left Pane)
        self.inventory_view = InventoryView(
            on_part_selected_callback=self._on_part_selected
        )
        sidebar_page = Adw.NavigationPage(
            title="Inventory", tag="inventory_sidebar"
        )
        sidebar_page.set_child(self.inventory_view)
        self.nav_split.set_sidebar(sidebar_page)

        # Detail View Widget (Right Pane)
        self.detail_view = DetailView(
            db=self.db,
            on_query_rag_callback=self._on_query_rag,
            on_quantity_changed_callback=self._on_quantity_changed_by_mpn,
            on_part_updated_callback=lambda _: self.refresh_inventory(),
        )
        content_page = Adw.NavigationPage(
            title="Part Details", tag="part_details"
        )
        content_page.set_child(self.detail_view)
        self.nav_split.set_content(content_page)

        # Charon Console Widget (Bottom/Side Drawer)
        self.console_view = CharonConsoleView(sdk_client=self.sdk_client)
        console_page = Adw.NavigationPage(
            title="Charon Assistant", tag="charon_console"
        )
        console_page.set_child(self.console_view)
        self.console_split.set_sidebar(console_page)

    # =========================================================================
    # SYNC & TELEMETRY HANDLERS
    # =========================================================================

    def _on_force_sync(self) -> bool:
        """Invoked when the user triggers a manual re-sync via the HeaderBar."""
        logger.info("Executing database sync via Charon SDK Client...")
        try:
            if hasattr(self.sdk_client, "sync_database"):
                success = self.sdk_client.sync_database()
            elif hasattr(self.sdk_client, "trigger_sync"):
                success = self.sdk_client.trigger_sync()
            else:
                success = True

            GLib.idle_add(self.refresh_inventory)
            return success
        except Exception as e:
            logger.error(f"Sync failed via Charon SDK: {e}")
            raise

    def _on_telemetry_event(self, event_data: dict):
        """Thread-safe handler for Charon WebSocket TelemetryBus events."""
        event_type = event_data.get("event")
        if event_type == "database_synced":
            logger.info("Received 'database_synced' event via WebSocket.")
            GLib.idle_add(self.refresh_inventory)

        # Forward telemetry payload to HeaderBar controller
        if hasattr(self, "header_bar"):
            self.header_bar.on_telemetry_event(event_data)

    # =========================================================================
    # ACTION HANDLERS & DIALOGS
    # =========================================================================

    def _on_refresh_action(self, action, param):
        """Action handler for win.refresh."""
        self.refresh_inventory()
        self.header_bar.refresh_sync_status()
        logger.info("Inventory manually refreshed via app menu.")

    def _on_preferences_action(self, action, param):
        """Action handler for win.preferences."""
        prefs = Adw.PreferencesWindow(transient_for=self)

        # General Page
        page_general = Adw.PreferencesPage(
            title="General", icon_name="settings-symbolic"
        )

        db_group = Adw.PreferencesGroup(
            title="Database & Storage",
            description="Manage local SQLite inventory state.",
        )
        auto_save_row = Adw.SwitchRow(
            title="Auto-Sync Stock Changes",
            subtitle="Persist quantity edits immediately to local storage",
        )
        auto_save_row.set_active(True)
        db_group.add(auto_save_row)
        page_general.add(db_group)

        # Charon AI Page
        page_ai = Adw.PreferencesPage(
            title="Charon SDK", icon_name="utilities-terminal-symbolic"
        )
        ai_group = Adw.PreferencesGroup(title="Gateway Endpoint")
        gateway_entry = Adw.EntryRow(title="SDK Gateway URL")
        gateway_entry.set_text("http://localhost:8000")
        ai_group.add(gateway_entry)
        page_ai.add(ai_group)

        prefs.add(page_general)
        prefs.add(page_ai)
        prefs.present()

    def _on_about_action(self, action, param):
        """Action handler for win.about."""
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="PartVault",
            application_icon="package-x-generic-symbolic",
            developer_name="PartVault Engineering",
            version="0.1.0",
            comments="Modern electronic component inventory manager powered by Charon AI Gateway.",
            website="https://github.com/example/partvault",
            issue_url="https://github.com/example/partvault/issues",
            copyright="© 2026 PartVault Developers",
            license_type=Gtk.License.GPL_3_0,
        )
        about.present()

    def refresh_inventory(self):
        """Re-queries database records and updates the InventoryView grid."""
        parts = self.db.get_all_parts()
        self.inventory_view.populate(parts)

    def _on_part_selected(self, part: PartModel):
        if self._active_part and self._qty_notify_handler_id:
            self._active_part.disconnect(self._qty_notify_handler_id)
            self._qty_notify_handler_id = 0

        self._active_part = part
        self.detail_view.bind_part(part)

        if part:
            self._qty_notify_handler_id = part.connect(
                "notify::quantity", self._on_quantity_changed_in_ui
            )

    def _on_quantity_changed_by_mpn(self, mpn: str, new_qty: int):
        self.db.update_quantity(mpn, new_qty)
        logger.info(f"Persisted stock update for MPN '{mpn}': {new_qty}")

    def _on_quantity_changed_in_ui(self, part: PartModel, param):
        self.db.update_quantity(part.mpn, part.quantity)
        logger.info(
            f"Persisted property notification change for '{part.mpn}': {part.quantity}"
        )

    def _on_query_rag(self, prompt: str):
        """Triggers RAG spec search via Charon and passes active component context."""
        self.console_split.set_collapsed(False)
        if hasattr(self.header_bar, "console_toggle_btn"):
            self.header_bar.console_toggle_btn.set_active(True)

        context_data = {}
        if self._active_part:
            context_data["active_part"] = {
                "mpn": self._active_part.mpn,
                "manufacturer": self._active_part.manufacturer,
                "description": self._active_part.description,
                "category": self._active_part.category,
                "footprint": self._active_part.package_footprint,
            }

        self.console_view.send_prompt(prompt, context=context_data)

    def _on_console_toggled(self, button: Gtk.ToggleButton):
        self.console_split.set_collapsed(not button.get_active())

    def _on_add_part_dialog(self, button):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Ingest New Component",
            body="Enter component specifications to persist in PartVault.",
        )

        group = Adw.PreferencesGroup()
        entry_mpn = Adw.EntryRow(title="MPN (e.g. STM32F401RE)")
        entry_mfr = Adw.EntryRow(title="Manufacturer (e.g. STMicroelectronics)")
        entry_desc = Adw.EntryRow(title="Description")
        entry_category = Adw.EntryRow(title="Category (e.g. Microcontroller)")
        entry_footprint = Adw.EntryRow(title="Package / Footprint (e.g. LQFP-64)")
        entry_bin = Adw.EntryRow(title="Bin Location (e.g. BIN-MCU-01)")
        entry_qty = Adw.EntryRow(title="Initial Quantity")
        entry_qty.set_text("1")

        group.add(entry_mpn)
        group.add(entry_mfr)
        group.add(entry_desc)
        group.add(entry_category)
        group.add(entry_footprint)
        group.add(entry_bin)
        group.add(entry_qty)

        dialog.set_extra_child(group)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Add Part")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def _on_dialog_response(dlg, response):
            if response == "save":
                mpn = entry_mpn.get_text().strip().upper()
                if not mpn:
                    return

                try:
                    qty = int(entry_qty.get_text().strip() or "0")
                except ValueError:
                    qty = 0

                new_part = PartModel(
                    mpn=mpn,
                    manufacturer=entry_mfr.get_text().strip(),
                    description=entry_desc.get_text().strip(),
                    category=entry_category.get_text().strip() or "General",
                    package_footprint=entry_footprint.get_text().strip(),
                    bin_location=entry_bin.get_text().strip() or "Unassigned",
                    quantity=qty,
                )

                if self.db.upsert_part(new_part):
                    self.inventory_view.add_part(new_part)
                    logger.info(f"Successfully ingested new component: {mpn}")
                else:
                    logger.error(f"Failed to persist component: {mpn}")

        dialog.connect("response", _on_dialog_response)
        dialog.present()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "partvault"
version = "0.1.0"
description = "Modern GNOME GTK4/Libadwaita inventory management application integrated with Charon AI."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
    { name = "Godvalve" }
]
keywords = ["gtk4", "libadwaita", "gnome", "inventory", "charon", "electronics", "rag"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Hardware",
]

dependencies = [
    "httpx>=0.28.1",
    "PyGObject>=3.42.0",
    "pygobject-stubs>=2.17.0",
    "websockets>=16.1.1",
]

[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
]

[project.gui-scripts]
partvault = "partvault.main:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["partvault*"]

# =========================================================================
# XDG DESKTOP & ICON ASSET INSTALLATION
# =========================================================================

[tool.setuptools.data-files]
"share/applications" = ["data/partvault.desktop"]
"share/icons/hicolor/scalable/apps" = ["assets/partvault.svg"]

# =========================================================================
# PYTEST CONFIGURATION
# =========================================================================

[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --import-mode=importlib --cov=partvault --cov-report=term-missing"
testpaths = [
    "tests",
]
python_files = [
    "test_*.py",
    "*_test.py",
]
python_classes = [
    "Test*",
]
python_functions = [
    "test_*",
]
log_cli = true
log_cli_level = "INFO"
filterwarnings = [
    "ignore::gi.PyGIDeprecationWarning",
    "ignore:.*unix_signal_add_full.*:DeprecationWarning",
]

# =========================================================================
# COVERAGE CONFIGURATION
# =========================================================================

[tool.coverage.run]
source = ["partvault"]
branch = true
omit = [
    "tests/*",
    "partvault/seed.py",
]

[tool.coverage.report]
show_missing = true
skip_covered = false
precision = 2
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "pass",
]

[tool.coverage.html]
directory = "htmlcov"

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/scripts/DB Seed.py`

```python
import logging
import sys
from pathlib import Path

from partvault.db import InventoryDatabase
from partvault.models.part import PartModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PartVault.Seed")

SAMPLE_PARTS = [
    PartModel(
        mpn="STM32F401RE",
        description="ARM Cortex-M4 MCU with 512KB Flash, 84MHz, LQFP-64",
        category="Microcontrollers",
        quantity=5,
        bin_location="MCU-01",
        min_threshold=2,
        datasheet_path="/usr/share/doc/datasheets/stm32f401re.pdf",
        mouser_url="https://www.mouser.com/Search/Refine?Keyword=STM32F401RE",
    ),
    PartModel(
        mpn="ESP32-WROOM-32E",
        description="Wi-Fi + BLE MCU Module, 4MB SPI Flash, PCB Antenna",
        category="Microcontrollers",
        quantity=12,
        bin_location="MCU-02",
        min_threshold=5,
        datasheet_path="/usr/share/doc/datasheets/esp32-wroom-32e.pdf",
    ),
    PartModel(
        mpn="ATmega328P-PU",
        description="8-bit AVR Microcontroller, 32KB Flash, 20MHz, DIP-28",
        category="Microcontrollers",
        quantity=1,  # Low stock trigger
        bin_location="MCU-01",
        min_threshold=3,
    ),
    PartModel(
        mpn="AMS1117-3.3",
        description="1A Low Dropout Voltage Regulator, 3.3V Output, SOT-223",
        category="Power Management",
        quantity=45,
        bin_location="PWR-01",
        min_threshold=10,
    ),
    PartModel(
        mpn="BME280",
        description="Combined Humidity, Pressure and Temperature Sensor, I2C/SPI",
        category="Sensors",
        quantity=3,
        bin_location="SENS-01",
        min_threshold=2,
    ),
    PartModel(
        mpn="NE555P",
        description="Single Precision Timer, DIP-8",
        category="Analog ICs",
        quantity=20,
        bin_location="IC-01",
        min_threshold=5,
    ),
    PartModel(
        mpn="RES-10K-0805",
        description="10k Ohm 1% 1/8W Surface Mount Resistor 0805",
        category="Passives",
        quantity=250,
        bin_location="PASS-01",
        min_threshold=50,
    ),
    PartModel(
        mpn="CAP-100NF-50V-0805",
        description="100nF (0.1uF) 50V Ceramic Capacitor X7R 0805",
        category="Passives",
        quantity=0,  # Out of stock trigger
        bin_location="PASS-02",
        min_threshold=25,
    ),
    PartModel(
        mpn="2N7002",
        description="N-Channel 60V 115mA Enhancement Mode Field Effect Transistor SOT-23",
        category="Discretes",
        quantity=18,
        bin_location="DISC-01",
        min_threshold=10,
    ),
    PartModel(
        mpn="USB-C-RECEPTACLE-16P",
        description="USB Type-C Female 16-Pin Connector SMD/TH Hybrid",
        category="Connectors",
        quantity=8,
        bin_location="CONN-01",
        min_threshold=5,
    ),
]


def seed_database(db_path: Path = None):
    """Populates SQLite database with sample component hardware."""
    db = InventoryDatabase(db_path=db_path)
    logger.info("Seeding PartVault database...")

    added_count = 0
    skipped_count = 0

    for part in SAMPLE_PARTS:
        if db.add_part(part):
            added_count += 1
            logger.info(f"Inserted: {part.mpn} ({part.category})")
        else:
            skipped_count += 1
            logger.info(f"Skipped existing: {part.mpn}")

    logger.info(
        f"Seeding complete: {added_count} parts added, {skipped_count} skipped."
    )


if __name__ == "__main__":
    seed_database()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/scripts/test_headless_e2e.py`

```python
#!/usr/bin/env python3
"""
Headless End-to-End Automated Test Suite for PartVault.
"""

import os
import sys
import tempfile
from pathlib import Path

# Force X11 software rendering under Xvfb and disable GLib/AT-SPI chatter
os.environ["GDK_BACKEND"] = "x11"
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
os.environ["NO_AT_BRIDGE"] = "1"
os.environ["GTK_A11Y"] = "none"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from partvault.db import InventoryDatabase
from partvault.models.part import PartModel
from partvault.sdk_client import CharonSDKClient


def run_tests() -> int:
    print("=" * 70)
    print("🚀 Running PartVault Headless E2E Automated Test Suite")
    print(f"   Database Class: {InventoryDatabase.__name__}")
    print("=" * 70)

    # 1. Initialize Libadwaita under Xvfb
    print("\n[1/4] Initializing GTK4 & Libadwaita (Xvfb Virtual Display)...")
    Adw.init()
    print("   ✓ Libadwaita initialized successfully.")

    # 2. Test Isolated SQLite Operations (ADR-0004)
    print("\n[2/4] Testing Database CRUD operations in temporary sandbox...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "e2e_sandbox.db"
        db = InventoryDatabase(db_path=db_file)

        # Insert test part
        test_part = PartModel(
            mpn="HEADLESS-01",
            description="Headless Verification IC",
            category="Testing",
            quantity=10,
            bin_location="BIN-TEST-01",
            min_threshold=2,
        )
        assert db.add_part(test_part) is True, "Failed to insert test part into SQLite"
        print("   ✓ Inserted part 'HEADLESS-01'")

        # Fetch part
        retrieved = db.get_part_by_mpn("HEADLESS-01")
        assert retrieved is not None, "Failed to retrieve part from SQLite"
        assert retrieved.quantity == 10, "Quantity mismatch on retrieval"
        print("   ✓ Retrieved and verified 'HEADLESS-01' parameters")

        # Update stock
        db.update_quantity("HEADLESS-01", 25)
        updated = db.get_part_by_mpn("HEADLESS-01")
        assert updated is not None and updated.quantity == 25, "Quantity update failed"
        print("   ✓ Updated stock level to 25")

        # Delete part
        assert db.delete_part("HEADLESS-01") is True, "Failed to delete part"
        assert db.get_part_by_mpn("HEADLESS-01") is None, "Part still exists after deletion"
        print("   ✓ Deleted part successfully")

    # 3. Test GTK4 UI Widget Hierarchy
    print("\n[3/4] Constructing GTK4 window & navigation hierarchy headlessly...")
    window = Adw.ApplicationWindow()
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    label = Gtk.Label(label="Headless Test Label")
    main_box.append(label)
    window.set_content(main_box)
    assert window.get_content() == main_box, "GTK Widget binding failed"
    print("   ✓ GTK4 UI window and widget tree allocated without errors")

    # 4. Test Async Gateway Client Initialization (ADR-0002)
    print("\n[4/4] Testing CharonSDKClient background worker state...")
    sdk_client = CharonSDKClient(client_id="e2e_test_runner")
    assert sdk_client._thread.is_alive(), "SDK Client background thread failed to start"
    print(f"   ✓ CharonSDKClient initialized (Thread Alive: {sdk_client._thread.is_alive()})")
    sdk_client.shutdown()

    print("\n" + "=" * 70)
    print("🎉 ALL HEADLESS E2E TESTS PASSED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_tests())
    except Exception as err:
        print(f"\n❌ Headless E2E Test Failed with Exception: {err}", file=sys.stderr)
        sys.exit(1)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/tests/RUN TESTS.md`

```markdown
pytest tests/test_sdk_client.py -v

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/tests/test_db.py`

```python
from pathlib import Path
import pytest

from partvault.db import InventoryDatabase
from partvault.models.part import PartModel


@pytest.fixture
def db(tmp_path: Path) -> InventoryDatabase:
    """Fixture providing an isolated InventoryDatabase instance per test."""
    test_db_path = tmp_path / "test_quartermaster.db"
    return InventoryDatabase(db_path=test_db_path)


@pytest.fixture
def sample_part() -> PartModel:
    """Fixture providing a standard PartModel instance."""
    return PartModel(
        mpn="STM32F401RE",
        description="ARM Cortex-M4 MCU 84MHz",
        category="Microcontrollers",
        quantity=5,
        bin_location="BIN-MCU-01",
        min_threshold=2,
        datasheet_path="/tmp/stm32f401re.pdf",
        mouser_url="https://mouser.com/search?q=STM32F401RE",
    )


# =========================================================================
# INITIALIZATION & SCHEMA TESTS
# =========================================================================

def test_db_initialization(tmp_path: Path):
    """Verifies that the database file and schema are initialized automatically."""
    db_path = tmp_path / "init_test.db"
    db = InventoryDatabase(db_path=db_path)

    assert db_path.exists()
    assert db.get_all_parts() == []


# =========================================================================
# CREATE (INSERT) TESTS
# =========================================================================

def test_add_part_success(db: InventoryDatabase, sample_part: PartModel):
    """Tests successful insertion of a new part."""
    success = db.add_part(sample_part)
    assert success is True

    retrieved = db.get_part_by_mpn("STM32F401RE")
    assert retrieved is not None
    assert retrieved.mpn == "STM32F401RE"
    assert retrieved.description == "ARM Cortex-M4 MCU 84MHz"
    assert retrieved.quantity == 5


def test_add_duplicate_mpn_fails(db: InventoryDatabase, sample_part: PartModel):
    """Tests that inserting a duplicate primary key (MPN) returns False."""
    assert db.add_part(sample_part) is True
    # Second attempt with same MPN
    assert db.add_part(sample_part) is False


# =========================================================================
# READ TESTS
# =========================================================================

def test_get_part_by_mpn_nonexistent(db: InventoryDatabase):
    """Verifies that querying a non-existent MPN returns None."""
    assert db.get_part_by_mpn("NONEXISTENT_MPN") is None


def test_get_all_parts_sorted(db: InventoryDatabase):
    """Verifies that get_all_parts retrieves all parts ordered alphabetically by MPN."""
    part1 = PartModel(mpn="NE555P", description="Timer IC", category="Analog ICs")
    part2 = PartModel(mpn="AMS1117-3.3", description="LDO Voltage Regulator", category="Power")

    db.add_part(part1)
    db.add_part(part2)

    parts = db.get_all_parts()
    assert len(parts) == 2
    assert parts[0].mpn == "AMS1117-3.3"
    assert parts[1].mpn == "NE555P"


# =========================================================================
# UPDATE TESTS
# =========================================================================

def test_update_part(db: InventoryDatabase, sample_part: PartModel):
    """Tests updating part properties."""
    db.add_part(sample_part)

    # Modify properties on the object
    sample_part.quantity = 15
    sample_part.bin_location = "BIN-MCU-02"
    sample_part.description = "Updated Description"

    updated = db.update_part(sample_part)
    assert updated is True

    retrieved = db.get_part_by_mpn("STM32F401RE")
    assert retrieved.quantity == 15
    assert retrieved.bin_location == "BIN-MCU-02"
    assert retrieved.description == "Updated Description"


def test_update_quantity_direct(db: InventoryDatabase, sample_part: PartModel):
    """Tests quick quantity update function."""
    db.add_part(sample_part)

    updated = db.update_quantity("STM32F401RE", 42)
    assert updated is True

    retrieved = db.get_part_by_mpn("STM32F401RE")
    assert retrieved.quantity == 42


def test_update_nonexistent_part(db: InventoryDatabase, sample_part: PartModel):
    """Verifies updating a non-existent part returns False."""
    assert db.update_part(sample_part) is False
    assert db.update_quantity("NONEXISTENT", 10) is False


# =========================================================================
# DELETE TESTS
# =========================================================================

def test_delete_part_success(db: InventoryDatabase, sample_part: PartModel):
    """Tests removing a part record."""
    db.add_part(sample_part)
    assert db.get_part_by_mpn("STM32F401RE") is not None

    deleted = db.delete_part("STM32F401RE")
    assert deleted is True
    assert db.get_part_by_mpn("STM32F401RE") is None


def test_delete_nonexistent_part(db: InventoryDatabase):
    """Verifies deleting a non-existent part returns False."""
    assert db.delete_part("NONEXISTENT") is False
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/tests/test_part_model.py`

```python
import pytest
from partvault.models.part import PartModel


# =========================================================================
# INITIALIZATION TESTS
# =========================================================================

def test_part_model_defaults():
    """Verifies default values when instantiating PartModel with minimal arguments."""
    part = PartModel(mpn="STM32F401RE")

    assert part.mpn == "STM32F401RE"
    assert part.description == ""
    assert part.category == "General"
    assert part.quantity == 0
    assert part.bin_location == "Unassigned"
    assert part.min_threshold == 2
    assert part.datasheet_path == ""
    assert part.mouser_url == ""


def test_part_model_custom_init():
    """Verifies initializing PartModel with explicit arguments."""
    part = PartModel(
        mpn="ESP32-WROOM-32E",
        description="Wi-Fi BLE Module",
        category="Microcontrollers",
        quantity=15,
        bin_location="BIN-MCU-02",
        min_threshold=5,
        datasheet_path="/docs/esp32.pdf",
        mouser_url="https://mouser.com/esp32",
    )

    assert part.mpn == "ESP32-WROOM-32E"
    assert part.description == "Wi-Fi BLE Module"
    assert part.category == "Microcontrollers"
    assert part.quantity == 15
    assert part.bin_location == "BIN-MCU-02"
    assert part.min_threshold == 5
    assert part.datasheet_path == "/docs/esp32.pdf"
    assert part.mouser_url == "https://mouser.com/esp32"


# =========================================================================
# SERIALIZATION & DESERIALIZATION TESTS
# =========================================================================

def test_part_model_to_dict():
    """Verifies converting a PartModel GObject to a standard Python dictionary."""
    part = PartModel(
        mpn="NE555P",
        description="Precision Timer IC",
        category="Analog ICs",
        quantity=20,
        bin_location="IC-01",
        min_threshold=3,
        datasheet_path="/docs/ne555.pdf",
        mouser_url="https://mouser.com/ne555",
    )

    d = part.to_dict()

    assert isinstance(d, dict)
    assert d["mpn"] == "NE555P"
    assert d["description"] == "Precision Timer IC"
    assert d["category"] == "Analog ICs"
    assert d["quantity"] == 20
    assert d["bin_location"] == "IC-01"
    assert d["min_threshold"] == 3
    assert d["datasheet_path"] == "/docs/ne555.pdf"
    assert d["mouser_url"] == "https://mouser.com/ne555"


def test_part_model_from_dict():
    """Verifies constructing a PartModel GObject from a dictionary (e.g. SQLite row)."""
    row_dict = {
        "mpn": "AMS1117-3.3",
        "description": "3.3V LDO Voltage Regulator",
        "category": "Power Management",
        "quantity": 50,
        "bin_location": "PWR-01",
        "min_threshold": 10,
        "datasheet_path": "/docs/ams1117.pdf",
        "mouser_url": "https://mouser.com/ams1117",
    }

    part = PartModel.from_dict(row_dict)

    assert isinstance(part, PartModel)
    assert part.mpn == "AMS1117-3.3"
    assert part.description == "3.3V LDO Voltage Regulator"
    assert part.category == "Power Management"
    assert part.quantity == 50
    assert part.bin_location == "PWR-01"
    assert part.min_threshold == 10
    assert part.datasheet_path == "/docs/ams1117.pdf"
    assert part.mouser_url == "https://mouser.com/ams1117"


# =========================================================================
# GOBJECT SIGNAL & PROPERTY NOTIFICATION TESTS
# =========================================================================

def test_part_model_notify_quantity_signal():
    """Verifies PyGObject emits 'notify::quantity' signal when quantity changes."""
    part = PartModel(mpn="2N7002", quantity=10)
    signal_received = []

    def on_notify_quantity(gobj, pspec):
        signal_received.append((gobj.mpn, gobj.quantity))

    part.connect("notify::quantity", on_notify_quantity)

    # Trigger property update
    part.quantity = 12

    assert len(signal_received) == 1
    assert signal_received[0] == ("2N7002", 12)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `/home/godvalve/Projects/Tools/PartVault/tests/test_sdk_client.py`

```python
# tests/test_sdk_client.py
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from partvault.sdk_client import CharonSDKClient, WSEvent


def wait_for_condition(condition_fn, timeout: float = 2.0) -> bool:
    """Helper to poll for async worker completion across threads."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_fn():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def mock_glib_idle():
    """Patches GLib.idle_add to execute callbacks immediately on the calling thread."""
    with patch("partvault.sdk_client.GLib.idle_add") as mock_idle:
        mock_idle.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
        yield mock_idle


@pytest.fixture
def mock_ws_connect():
    """Provides a valid async context manager mock for websockets.connect."""
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = asyncio.CancelledError

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_ws)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("websockets.connect", return_value=ctx) as mock_connect:
        yield mock_connect, mock_ws


@pytest.fixture
def client(mock_glib_idle, mock_ws_connect):
    """Provides a fresh CharonSDKClient instance with WebSockets cleanly mocked."""
    client_instance = CharonSDKClient(
        client_id="test_client_001",
        base_url="http://localhost:8000",
        api_key="sk_test_12345",
    )
    yield client_instance
    client_instance.shutdown()


# ==============================================================================
# TEST CASES
# ==============================================================================

class TestCharonSDKClientInitialization:
    """Verifies default parameters and header formatting."""

    def test_initialization_defaults_and_properties(self, client):
        assert client.client_id == "test_client_001"
        assert client.base_url == "http://localhost:8000"
        assert client.ws_url == "ws://localhost:8000/v1/ws?client_id=test_client_001&api_key=sk_test_12345"
        assert client.headers == {"X-API-Key": "sk_test_12345"}
        assert client._thread.is_alive()


class TestCallbackRegistrationAndDispatch:
    """Verifies event handler registration and GTK main thread dispatching."""

    def test_register_and_dispatch_ui_callback(self, client, mock_glib_idle):
        received_events = []

        def event_handler(event: WSEvent):
            received_events.append(event)

        client.register_ui_callback("task_stream", event_handler)
        client.register_ui_callback("*", event_handler)

        test_event = WSEvent(event_type="task_stream", task_id="task_99", data={"message": "hello"})
        client._dispatch_to_gtk("task_stream", test_event)

        assert mock_glib_idle.call_count == 2
        assert len(received_events) == 2
        assert received_events[0].task_id == "task_99"


class TestSubmitTaskAsync:
    """Verifies REST task submission under success and failure modes."""

    @patch("httpx.AsyncClient.post")
    def test_submit_task_success(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": "task_123",
            "status": "executing",
            "message": "Task received",
        }
        mock_post.return_value = mock_response

        results = []

        def callback(success: bool, response_or_err: str):
            results.append((success, response_or_err))

        client.submit_task_async(
            prompt="Audit inventory for MCU-01",
            callback=callback,
            context={"category": "microcontrollers"},
            agent_override="The_Quartermaster",
        )

        assert wait_for_condition(lambda: len(results) > 0)
        success, data = results[0]

        assert success is True
        assert data["task_id"] == "task_123"

    @patch("httpx.AsyncClient.post")
    def test_submit_task_http_error(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        results = []

        def callback(success: bool, response_or_err: str):
            results.append((success, response_or_err))

        client.submit_task_async(prompt="Faulty command", callback=callback)

        assert wait_for_condition(lambda: len(results) > 0)
        success, err_msg = results[0]

        assert success is False
        assert "HTTP 500" in err_msg


class TestGatekeeperRespondAsync:
    """Verifies human-in-the-loop authorization REST calls."""

    @patch("httpx.AsyncClient.post")
    def test_respond_gatekeeper_success(self, mock_post, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "approved"}'
        mock_post.return_value = mock_response

        results = []

        def callback(success: bool, response_text: str):
            results.append((success, response_text))

        client.respond_gatekeeper_async(
            approval_id="app_abc123",
            decision="proceed",
            notes="Authorized by operator",
            callback=callback,
        )

        assert wait_for_condition(lambda: len(results) > 0)
        success, text = results[0]

        assert success is True
        assert '{"status": "approved"}' in text


class TestWebSocketListener:
    """Verifies parsing of incoming WebSocket JSON payloads into WSEvents."""

    def test_websocket_message_reception(self, mock_glib_idle):
        raw_json_message = json.dumps({
            "event_type": "gatekeeper_intercept",
            "task_id": "task_777",
            "data": {"approval_id": "app_555", "action": "Wipe Flash Memory"},
        })

        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [raw_json_message, asyncio.CancelledError()]

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_ws)
        ctx.__aexit__ = AsyncMock(return_value=None)

        received_events = []

        with patch("websockets.connect", return_value=ctx):
            client_instance = CharonSDKClient(client_id="ws_tester")
            client_instance.register_ui_callback("gatekeeper_intercept", lambda e: received_events.append(e))

            assert wait_for_condition(lambda: len(received_events) > 0)

            event = received_events[0]
            assert event.event_type == "gatekeeper_intercept"
            assert event.task_id == "task_777"
            assert event.data["approval_id"] == "app_555"

            client_instance.shutdown()
```

────────────────────────────────────────────────────────────────────────────────

