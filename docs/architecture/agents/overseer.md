# Agent Card: `The_Overseer` (System Maintenance & Diagnostics)

**File Path:** `docs/architecture/agents/overseer.md`

**Target Module:** `charon/agents/overseer/agent.py`

**Agent Class:** `TheOverseer`

**Agent Enum:** `AgentEnum.The_Overseer`

**Safety Intercept Level:** 🟡 **Medium Intercept** (Approval required for destructive log purges or manual full-system maintenance commands)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Overseer`** serves as Charon’s system maintenance, health monitoring, and workspace hygiene agent. It maintains database integrity, audits vector stores, reclaims storage from stale cache and log files, cleans orphaned project assets, and tracks real-time host hardware telemetry (CPU, RAM, disk utilization).

In addition to being triggered on-demand via intent requests, `The_Overseer` operates via systemd background services (`charond-overseer.service` and `charond-overseer.timer`) to perform scheduled daily system maintenance without interrupting standard user operations.

---

## 2. Action Capabilities & Method Mapping

| Action (`OverseerPayload`) | Executing Method | Description |
| --- | --- | --- |
| `optimize_databases` | `optimize_sqlite_db` | Runs `PRAGMA integrity_check`, `PRAGMA optimize`, `PRAGMA wal_checkpoint(TRUNCATE)`, and `VACUUM` on SQLite databases. |
| `audit_vector_store` | `audit_vector_store` | Inspects ChromaDB directory structure, SQLite quick check, collection counts, and folder integrity. |
| `prune_logs_and_cache` | `prune_logs_and_cache` | Sweeps log files and temporary cache items older than `prune_days` (default: 7 days) and reclaims disk space. |
| `prune_orphaned_assets` | `prune_orphaned_assets` | Identifies and removes broken symlinks and unlinked PDF datasheets not registered in `quartermaster.db`. |
| `get_system_health` | `get_system_health` | Samples host hardware stats via `psutil` (CPU, RAM, RSS memory), disk free space, and database file sizes. |
| `run_full_maintenance` | `execute("run_full_maintenance")` | Sequentially executes all optimization, auditing, pruning, and telemetry routines in a single batch operation. |

---

## 3. Detailed Subsystem Logic

### Database Optimization (`optimize_sqlite_db`)

* **Target Resolution:** Resolves targets via `_resolve_target_databases()`, auto-detecting `quartermaster.db` and `chroma.sqlite3` unless explicit file/folder paths are provided.
* **Integrity Enforcement:**
1. Executes `PRAGMA integrity_check;` — aborts with `"corrupted"` status if validation fails.
2. Executes `PRAGMA foreign_key_check;` to capture relational anomalies.
3. Executes `PRAGMA optimize;` to update SQLite query planner statistics.
4. Truncates Write-Ahead Logs (`PRAGMA wal_checkpoint(TRUNCATE);`).
5. Runs `VACUUM;` to reclaim unused disk pages and calculates `bytes_freed`.



### Vector Store Audit (`audit_vector_store`)

* Validates `CHROMA_DB_DIR` directory existence and measures `chroma.sqlite3` binary file size.
* Runs SQLite `PRAGMA quick_check;` and queries table meta-data to report total active collections and physical collection directory count on disk.

### Workspace & Log Hygiene (`prune_logs_and_cache` & `prune_orphaned_assets`)

* **Log & Cache Pruning:** Traverses `LOGS_DIR` and `DATA_DIR/cache`. Files with modification times older than $T_{\text{cutoff}} = \text{now} - (\text{prune\_days} \times 86400)$ are unlinked.
* **Orphaned Datasheet Sweep:** Cross-references physical files in `DATA_DIR/datasheets` against registered entries in `quartermaster.db`. Deletes broken symlinks and unindexed orphan PDF files.

### Host Telemetry & Diagnostics (`get_system_health`)

Gathers real-time host metrics offloaded to an asynchronous thread:

* **Process & System RAM:** Samples `psutil.virtual_memory()` and tracks daemon RSS memory footprint (`proc.memory_info().rss`).
* **CPU Load:** Tracks system CPU usage and process-level CPU percentages.
* **Disk Usage:** Leverages `shutil.disk_usage()` on the primary system volume to track total, used, and free capacity in gigabytes.

---

## 4. Systemd Background Automation (`deploy/`)

`The_Overseer` is integrated directly into Linux `systemd` to run scheduled maintenance during low-activity windows (03:30 AM daily).

### Service Unit (`../../../deploy/systemd/charond-overseer.service`)

```ini
[Unit]
Description=Charon Overseer Background Maintenance & Diagnostics
Documentation=https://github.com/your-repo/charon
After=network.target

[Service]
Type=oneshot
WorkingDirectory=%h/Projects/Tools/Charon
Environment=PYTHONPATH=%h/Projects/Tools/Charon
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/Projects/Tools/Charon/.venv/bin/python %h/Projects/Tools/Charon/scripts/overseer_runner.py --action run_full_maintenance
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target

```

### Timer Unit (`../../../deploy/systemd/charond-overseer.timer`)

```ini
[Unit]
Description=Run Charon Overseer Maintenance Daily

[Timer]
# Run daily at 03:30 AM local time
OnCalendar=*-*-* 03:30:00
# Prevent load spikes on system boot if missed
Persistent=true
# Spread out execution within a 15-minute window
RandomizedDelaySec=900

[Install]
WantedBy=timers.target

```

---

## 5. Execution Integration Example

```python
from charon.agents.overseer import TheOverseer

overseer = TheOverseer()

# Run full system maintenance asynchronously
maintenance_report = await overseer.execute(
    action="run_full_maintenance",
    params={"prune_days": 14, "datasheets_dir": "/path/to/datasheets"}
)

print(f"Bytes Freed: {maintenance_report['database_optimization']['total_bytes_freed']}")
print(f"System Health: {maintenance_report['system_health']['telemetry']}")

```