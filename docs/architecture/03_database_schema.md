# CHARON — Persistence Layer & Database Schema Specification

This specification documents the live SQLite databases, vector store indices, and planned schema extensions managed under Charon's XDG data directory (`~/.local/share/charon/`).

---

## 1.0 Subsystem Overview & Path Mapping

Charon segregates state, telemetry, and domain memory across distinct, isolated storage engines defined in `charon/config/paths.py`:

| Database / Dir | Environment Path | Engine | Primary Responsibility |
| :--- | :--- | :--- | :--- |
| `charon_state.db` | `STATE_DB_PATH` | SQLite (WAL Mode) | Active task execution state, step progress, and capability indices. |
| `charon_ledger.db` | `LEDGER_DB_PATH` | SQLite (WAL Mode) | Append-only execution history, telemetry traces, and audit logs. |
| `chroma_db/` | `CHROMA_DB_DIR` | Chroma Vector DB | Long-term semantic embeddings and document retrieval (RAG). |
| `partvault.db` | `QUARTERMASTER_DB_PATH` | SQLite (WAL Mode) | External physical inventory database managed via `The_Quartermaster`. |

---

## 2.0 `charon_state.db` (Operational Runtime State)

* **Path**: `~/.local/share/charon/charon_state.db`
* **Access Mode**: SQLite WAL Mode (`PRAGMA journal_mode=WAL`)

### 2.1 Table: `task_state` (Audited Baseline)
Stores active and historical task orchestrations, execution progress, step counters, and client metadata.

```sql
CREATE TABLE task_state (
    task_id TEXT PRIMARY KEY,
    client_id TEXT,
    prompt TEXT NOT NULL,
    agent_override TEXT,
    status TEXT NOT NULL,
    current_step_index INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    plan_json TEXT,
    results_json TEXT,
    active_approval_id TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 Table: `skill_registry` (Planned Extension — Task 3)
Compiled index of dynamic agent skills discovered across search paths (`charon/skills/dynamic/`, `charon/skills/staged/`, `~/.local/share/charon/skills/`).

```sql
CREATE TABLE IF NOT EXISTS skill_registry (
    action_name TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    shelf_tags TEXT NOT NULL,          -- JSON array e.g. '["The_Spark", "The_Engineer"]'
    system_requirements TEXT NOT NULL, -- JSON array e.g. '["kicad-cli"]'
    entry_file_path TEXT NOT NULL,    -- Absolute path to plugin.py
    handler_name TEXT NOT NULL,       -- Entrypoint method inside plugin.py
    is_active INTEGER DEFAULT 1,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 Table: `skill_gaps` (Planned Extension — Task 4)
Logs missing agent capabilities to trigger automated blueprint staging (`charon/skills/staged/`) when failure count thresholds ($\ge 3$) are reached.

```sql
CREATE TABLE IF NOT EXISTS skill_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_name TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    gap_count INTEGER DEFAULT 1,
    last_occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(action_name, agent_name)
);
```

---

## 3.0 `charon_ledger.db` (Audit Trail & Telemetry)

* **Path**: `~/.local/share/charon/charon_ledger.db`
* **Access Mode**: SQLite WAL Mode (`PRAGMA journal_mode=WAL`)

### 3.1 Table: `audit_ledger` (Audited Baseline)
Provides an immutable event log for execution steps, tool invocations, token consumption, and WebSocket telemetry stream events.

```sql
CREATE TABLE audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    agent TEXT,
    tool_name TEXT,
    data_json TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_task ON audit_ledger(task_id);
```