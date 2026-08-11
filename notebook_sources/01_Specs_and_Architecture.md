# Subsystem Domain Context: 01_Specs_and_Architecture
> **Generated:** 2026-08-10 05:34 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `main` | **Commit:** `bc5f379`

---

## Target File: `README.md`

```markdown
# Charon (Digital Concierge)

**Privacy-first, local multi-agent AI orchestration daemon for Linux.**

Charon functions as an intelligent OS concierge running quietly in the background (`charond`). It orchestrates specialized AI agents to handle mechatronic hardware design (KiCad/PlatformIO), CAD/CAM digital fabrication (STEP/STL/G-code), system maintenance, web reconnaissance, vector memory indexing, and IoT automation.

For the full architectural charter, agent fleet description, and system vision, please consult [`docs/architecture/00_system_overview.md`](docs/architecture/00_system_overview.md).

---

## 🚀 Quickstart

### 1. Installation & Environment Setup
Ensure Python 3.12+ is installed on Linux:


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/adrs/adr-001-multi-agent-architecture.md`

```markdown
ADR-001: Local Multi-Agent Architecture with Modular PEP 562 Lazy Loading

    Status: Accepted

    Date: 2026-07-30

    Context:
    Monolithic LLM prompts struggle with bloated toolsets and context saturation when managing complex, multi-domain desktop tasks (EDA hardware design, CAD fabrication, OS maintenance, IoT control). Always-on agent frameworks waste substantial system memory when idle on a developer machine.

    Decision:
    Implement a modular multi-agent fleet coordinated by a central Triage Router. Agents are dynamically loaded using PEP 562 lazy-loaded modules, importing heavy libraries (e.g., CAD parsers, web scraping drivers, vector databases) only when an agent is actively invoked.

    Consequences:

        Positive: Drastically reduces charond startup time and idle RAM usage; isolates domain-specific context prompts to specialized agents.

        Negative: Introduces a small first-call latency penalty when an agent module is imported for the first time in a session.

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/adrs/adr-002-systemd-process-isolation.md`

```markdown
Status: Accepted

Date: 2026-07-30

Context:
To be useful as a workstation concierge, Charon must read and modify files on the real host OS. However, running an LLM agent with unrestricted system root access risks accidental system corruption (e.g., hallucinated rm -rf or overwriting /etc). Sandboxing the agent in a virtual machine or container renders host system management useless.

Decision:
Run charond natively on the host as a systemd --user service with kernel-enforced isolation (ProtectSystem=strict). The entire root filesystem (/, /usr, /etc, /var) is bind-mounted as Read-Only, while $HOME, /tmp, and /run/user/%U remain Read-Write.

Consequences:

    Positive: Provides total protection against catastrophic system mutations at the Linux kernel level without requiring VM/Docker overhead or locking the agent out of the user's workspace.

    Negative: Operations modifying system configurations outside $HOME (e.g., apt install) require escalation mechanisms (pkexec or Gatekeeper approvals).

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/adrs/adr-003-tiered-risk-matrix.md`

```markdown
Status: Accepted

Date: 2026-07-30

Context:
Not all OS actions carry equal risk. Read-only commands (cat, ls) should execute instantly with zero latency, while actions like modifying system services (systemctl) or executing generated code require human-in-the-loop validation.

Decision:
Implement a GatekeeperManager that evaluates action payloads against a 4-Tier Execution Risk Matrix:

    Level 0 (Read-Only): Auto-executed silently.

    Level 1 (Workspace Write): Auto-executed in $HOME with event logging.

    Level 2 (System Operations): Paused; triggers desktop/WebSocket confirmation dialogs.

    Level 3 (High-Risk/Root): Blocked for manual pass-through.

Consequences:

    Positive: Keeps the user in control of high-impact changes without causing friction on routine read/write queries.

    Negative: Multi-step workflows pause when hitting Level 2 actions until the user responds to the authorization prompt.

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/adrs/adr-004-event-driven-gateway.md`

```markdown
Status: Accepted

Date: 2026-07-30

Context:
Multiple frontends (GNOME Shell extensions, desktop UI, charon CLI) need real-time streaming logs, task progress updates, and prompt ingestion without blocking long-running orchestration loops.

Decision:
Expose a unified FastAPI gateway backed by an internal asyncio.Queue worker loop and WebSocket event broadcasting (EventEmitter). WebSockets handle bidirectional real-time events (token streaming, gatekeeper prompts), while HTTP endpoints accept task submissions.

Consequences:

    Positive: Completely decouples network ingress/egress from LLM inference and agent execution pipelines; enables multi-client monitoring.

    Negative: Requires strict state management across clients and handling disconnected WebSocket connections during task execution.

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/adrs/adr-005-dag-task-decomposition.md`

```markdown
Status: Accepted

Date: 2026-07-30

Context:
Complex user directives require coordinating multiple agents sequentially (e.g., Scout scrapes data → Spark generates schematics → Quartermaster verifies inventory). Passing raw conversational context between steps bloats context windows and increases drift.

Decision:
The Planner agent decomposes complex tasks into sequential Directed Acyclic Graph (DAG) plans. Step parameters support dynamic string variable substitution (e.g., $STEP_1_OUTPUT). Step failures trigger a self-healing loop via The Planner (diagnose action) or escalate to The Engineer.

Consequences:

    Positive: Keeps local LLM context windows lean and focused; handles multi-agent workflows; self-corrects transient errors automatically.

    Negative: Multi-step execution adds latency and multiple inference passes per overall request.

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/00_system_overview.md`

```markdown
# Charon System Architecture & Design Specification

> **System Overview & Architectural Blueprint**  
> Unified master specification combining runtime execution models, security boundaries, subsystem maps, AST import graphs, and code maintenance principles.

---

## 🪙 1. Executive Summary & Core Pillars

**Charon** is a local, privacy-first, multi-agent AI orchestration platform and OS companion. Designed to run seamlessly as a Linux background daemon (`charond`, dubbed *The Continental*), it acts as an intelligent, high-efficiency concierge for system task execution, hardware design, home automation, and workflow management.

Rather than relying on a single monolithic LLM prompt or rigid single-shot classification, Charon uses a modular architecture where a central engine triages natural language requests against agent capability manifests and delegates them to specialized, tool-equipped agents through a dynamic Plan-Execute-Evaluate loop.

### Key Pillars of the System

1. **Central Daemon, Persistence & Gateway (`charond` — "The Continental"):**
  
  - **Background Service Core:** Operates as a `systemd` user service (`charond.service`) running FastAPI and WebSockets for low-latency IPC. Supported by scheduled oneshot diagnostics (`charon-overseer.service`).
  
  - **Persistent State Machine & Audit Ledger:** Features crash-resilient SQLite/WAL task queues (`StateManager`, `PersistentTaskQueue`) and an append-only audit trail (`ExecutionLedger`), allowing daemon state recovery across restarts without losing task history.
  
  - **Kernel-Enforced Security:** Implements native systemd process isolation (`ProtectSystem=strict`). System root (`/`), `/usr`, and `/etc` are enforced as **Read-Only** to prevent accidental or hallucinated system damage, while granting explicit **Read-Write** access exclusively to `$HOME`, `/tmp`, and runtime sockets (`/run/user/%U`).
  
  - **IPC & Frontends:** Exposes real-time event channels to desktop extensions (GNOME Shell integration) and interactive terminal interfaces (`charon` CLI).
  
  - **Local Inference & Context Protection:** Interfaces directly with local LLM runtimes (via Ollama) with head-and-tail context window truncation to prevent large stdout/logs from saturating local contexts during multi-step runs.
  
2. **Hint-Guided Contract Negotiation & Stateful Reflection Loop:**
  
  - Prior to dispatching an execution turn, the `Coordinator` conducts a pre-turn contract negotiation (`negotiate_contract`). Incoming user prompt payloads, routing hints, and extracted parameters (e.g., target MPNs, requested binary viewers like `evince` or `xdg-open`) are evaluated against live-probed agent capabilities. Agents inspect candidate steps (`evaluate_capability`) and declare readiness before any system actions are taken.
  
  - Managed by the `Coordinator` and a shared `TaskBlackboard`, the system dynamically resolves step dependencies, automatically injects prerequisite capabilities into the requirement stack if missing artifacts are needed, and records produced artifacts across turns.
  
  - **4-Level Self-Healing Escalation Pathway:**
  

$$\text{[L1: Specialist Agent]} \longrightarrow \text{[L2: OS Automation]} \longrightarrow \text{[L3: Diagnostic Probe]} \longrightarrow \text{[L4: Engineer Fallback Script]}$$

- **Real-Time Telemetry Observability:** Streams structured trace events (`NEGOTIATION`, `EXECUTION`, `ESCALATION`, `SYSTEM`) via the `TelemetryBus` to terminal trace viewers (`charon.telemetry.viewer`) and desktop event channels.

3. **Manifest-Driven Orchestration & Dynamic Intent:**- Evaluates user intent using structured agent capability manifests (`AGENT_MANIFESTS`). Complex, multi-step, or context-dependent requests are handed off to `The_Planner` via a dynamic Plan-Execute-Evaluate loop rather than brittle single-shot routing.

---

## 2. Risk-Aware Execution Safety Policy

Tasks are routed through a tiered execution safety policy and human-in-the-loop approval pipeline (`Gatekeeper`):

| **Risk Level** | **Operations / Triggers** | **Execution Policy** |
| --- | --- | --- |
| **Level 0: Read-Only** | `cat`, `ls`, `grep`, `git status`, system queries | **Auto-execute** silently |
| **Level 1: Workspace Write** | `mkdir`, file edits, `git commit` within `$HOME` | **Auto-execute** + event log broadcast |
| **Level 2: System Ops** | `apt install`, `systemctl`, `/etc` configuration | **Desktop Pop-up / Gatekeeper Approval Required** |
| **Level 3: Critical / High Risk** | `sudo`, destructive operations (`dd`, `mkfs`) | **Hard Stop / Manual Terminal Pass-through** |

---

## 3. Execution Tiers & Subsystem Architecture

### 3.1 High-Level Execution Tiers


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/01_core_engine.md`

```markdown
# Core Execution Engine & Memory Architecture

**File Path:** `docs/architecture/01_core_engine.md`

**System Component:** Orchestration Engine, Orchestrator Brain, Double-Pass Intent Parser, Agent Dispatcher, Rolling RAM Conversation Buffer, and Schema Parsing Defense

**Target Modules:** `../../charon/core/session.py`, `../../charon/core/session.py`, `charon/core/parser.py`, `charon/core/dispatcher.py`, `charon/core/prompts.py`, `../../charon/intent/intent.py`, `charon/utils/memory.py`

**Protocol Specifications:** Core Engine v3.0 / Schema Spec v3.3 / Memory Architecture v2.0

---

## 1. Core Engine Pipeline Architecture (`charon/core/`)

The Core Engine provides the primary execution pipeline for Charon, translating natural language requests into deterministic agent executions, dynamic DAG workflows, and context-aware schema extraction.

```text
  User Prompt / Payload / SDK Request
                  │
                  ▼
      ┌───────────────────────┐
      │  OrchestrationEngine  │  <---> [Agent Override / Direct Pass]
      └───────────┬───────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │   Orchestrator Brain  │  <---> [ConversationBuffer: Rolling RAM Context]
      └───────────┬───────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │     IntentParser      │
      │  - Pass 1: Routing    │   ---> Selects target AgentEnum via Ollama
      │  - Pass 2: Extraction │   ---> Extracts parameters using agent payload schema
      └───────────┬───────────┘        (Injects ChromaDB ledger context)
                  │
                  ▼
      ┌───────────────────────┐
      │    AgentDispatcher    │   ---> Dynamic agent lookup (_resolve_agent)
      └───────────┬───────────┘   ---> Auto-chains RAG (Archivist -> Generalist)
                  │
                  ▼
       CHARON_ACK_MAP             ---> Selects thematic acknowledgment string

```

### Core Engine Subsystem Reference

* **`OrchestrationEngine` (`engine.py`):** High-level orchestration manager handling multi-step task planning, sequential step execution, `$STEP_X_OUTPUT` dynamic variable resolution, manual agent overrides, and self-healing exception handling.
* **`SessionGateway` (`session.py`):** Drives conversational context assembly, triggers double-pass intent parsing, injects vector store context rules, updates memory buffers, and generates thematic acknowledgments.
* **`IntentParser` (`parser.py`):** Executes the double-pass LLM routing and structured payload extraction process using local `llama3.1` inference.
* **`AgentDispatcher` (`dispatcher.py`):** Resolves agent enum definitions to concrete module classes (`_resolve_agent`), performs parameter fallback sanitization, auto-commits passive memory candidates, and manages agent output chaining.
* **`CHARON_ACK_MAP` (`prompts.py`):** A dictionary mapping each `AgentEnum` to randomized, personality-aligned acknowledgment responses for user feedback.

---

## 2. Double-Pass Intent Parsing & Schema Defense (`charon/core/parser.py`, `../../charon/intent/intent.py`)

### Double-Pass Parsing Flow

1. **Pass 1 (`parse_routing`):** Analyzes the raw prompt against current agent domain descriptions using Ollama to select the exact `AgentEnum`. Accepts exclusion lists to prevent re-routing into previously failed agents during self-healing loops.
2. **Pass 2 (`parse_extraction`):** Constructs a strict extraction prompt based on the target agent's Pydantic schema model. Injects relevant system rules retrieved from the ChromaDB vector ledger to enforce contextual boundaries.

### Defense-in-Depth Parsing Safeguards

To prevent structural extraction failures, JSON key wrapping, and `$defs` reference bugs common in local LLM outputs, `intent.py` enforces three defense layers:

1. **`StrictBaseModel` Isolation:** Payload schemas inherit from `StrictBaseModel` (`extra="ignore"`), dropping extra text explanations or hallucinated keys generated by the LLM.
2. **Schema Sanitization (`get_clean_schema()`):** Strips top-level JSON schema `$defs` definitions before sending schema prompts to Ollama, eliminating schema-reflection hallucinations.
3. **Pre-Validation Normalization (`sanitize_llm_payload`):** A `@model_validator(mode="before")` hook unwraps misplaced `"properties"` dictionaries and standardizes generic field names (e.g., mapping `query`, `prompt`, or `target_concept` into expected target fields).

---

## 3. Short-Term RAM Conversation Memory (`charon/utils/memory.py`)

`ConversationBuffer` provides short-term context tracking across multi-turn interactions using an in-memory rolling list of turn objects (`{"role": role, "content": content}`).

### Turn Window Truncation Logic

For a given configuration of $\text{max\_turns} = 5$, the memory buffer enforces a strict capacity limit of $N_{\text{max}}$ individual messages:

$$N_{\text{max}} = 2 \times \text{max\_turns} = 10 \text{ messages}$$

When $\text{len}(\text{history}) > N_{\text{max}}$, the buffer automatically prunes older context using Python slice operations (`history[-N_{\text{max}}:]`).

### Prompt Context Injection (`get_context_string()`)

Formats rolling history into standard speaker-labeled text blocks for LLM system prompt context injection, mapping `"user"` or `"human"` to `User` and all other roles to `Charon`:

```text
User: How do I compile firmware for the STM32 board?
Charon: The_Spark can compile firmware using compile_firmware.

```

---

## 4. Universal Passive Memory Harvesting (`../../charon/intent/intent.py`)

All agent payload schemas inherit from `BaseAgentPayload`, exposing an optional passive memory extraction model:

```python
class BaseAgentPayload(StrictBaseModel):
    requires_approval: bool = False
    memory_candidate: Optional[MemoryCandidate] = Field(
        default=None,
        description="Passive preference or system rule extracted from prompt context."
    )

```

$$\text{MemoryCandidate} = \{ \text{is\_persistent: bool}, \;\text{confidence: float}, \;\text{fact: str} \}$$

When a user mentions system configurations, personal preferences, or workspace rules in passing during routine requests, the parser extracts a `MemoryCandidate`. `AgentDispatcher` automatically detects this field and commits it to **The_Archivist** vector store without interrupting active task execution.

---

## 5. Autonomous Chaining & Self-Healing Error Protocols

* **Autonomous Blueprint Chaining:** When **`The_Planner`** completes a structural plan or build sequence (`draft_build_sequence` or `analyze_error_logs`), `OrchestrationEngine` automatically captures the plan output and routes execution to **`The_Engineer`** (`solve_edge_case`) without prompting the user.
* **Self-Healing Error Escalation:** If an agent encounters an unhandled runtime error during step execution, `OrchestrationEngine` catches the exception stack trace and escalates the issue to **`The_Planner`** (`diagnose`). The Planner analyzes the error, updates execution parameters, and re-issues the task to remedy the failure.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/02_gateway_and_ipc.md`

```markdown
# Gateway, IPC & Transport Architecture

**File Path:** `docs/architecture/02_gateway_and_ipc.md`

**System Component:** FastAPI Gateway, Asynchronous Task Queue, D-Bus System Service, WebSocket Event Bus, and Security Middleware

**Target Modules:** `charon/daemon.py`, `charon/gateway/`, `charon/dbus_server.py`, `charon/sdk.py`, `charon/cli.py`

**Protocol Specifications:** Gateway v3.1.0 / REST v1 / WebSockets / D-Bus `org.charon.Service`

---

## 1. Gateway & Daemon Architecture (`charon/daemon.py`, `charon/gateway/core.py`)

The API gateway hosts Charon’s primary communication layer under daemon version `3.1.0`. Access is controlled via constant-time header key checking alongside cross-origin resource sharing controls.


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/03_database_schema.md`

```markdown
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/_matrix.md`

```markdown
# Agent Ecosystem & Safety Intercept Matrix

**File Path:** `docs/architecture/agents/_matrix.md`

**Operational Scope:** Comprehensive routing, permission hierarchy, module mappings, and execution guardrails across all 12 specialist agents.

**System Specification:** Charon Schema Spec v3.3 / Agent Architecture v2.2

---

## 1. Master Agent Matrix

| Agent Enum | Target Module | Operational Domain | Primary Actions | Safety Intercept Level |
| --- | --- | --- | --- | --- |
| **`The_Spark`** | `charon/agents/spark/agent.py` | Firmware & EDA | `compile_firmware`, `flash_hardware`, `export_gerbers` | 🟡 Medium (Approval on `flash_hardware`) |
| **`The_Machinist`** | `charon/agents/machinist/agent.py` | Digital Fabrication | `export_cad_to_stl`, `generate_gcode`, `transmit_to_printer` | 🟡 Medium (Approval on `transmit_to_printer`) |
| **`The_Quartermaster`** | `charon/agents/quartermaster/agent.py` | Parts & Logistics | `generate_bom`, `fetch_datasheet`, `check_inventory`, `log_inventory` | 🟢 Low (Read-only / Non-destructive) |
| **`The_Cleaner`** | `charon/agents/cleaner/agent.py` | Workspace Hygiene | `initialize_project_workspace`, `commit_workspace`, `sweep_cad_iterations`, `list_workspaces`, `prune_logs`, `delete_project_workspace` | 🔴 High (Approval on `delete_project_workspace`) |
| **`The_Planner`** | `charon/agents/planner/agent.py` | Strategy & Blueprinting | `draft_build_sequence`, `decompose_task`, `diagnose`, `analyze_error_logs`, `resolve_workspace` | 🟢 Low (Auto-chains to `The_Engineer` / Execution DAG) |
| **`The_Archivist`** | `charon/agents/archivist/agent.py` | Vector Memory & RAG | `search_ledger`, `store_record`, `record_rule`, `expunge_record`, `delete_rule`, `summarize_ledger`, `index_datasheet`, `index_pdf`, `search_datasheets`, `query_datasheet` | 🟡 Medium (Approval on `expunge_record` / `delete_rule`) |
| **`The_Generalist`** | `charon/agents/generalist.py` | System & Q&A | `answer_query`, `calculate_math`, `acknowledge`, `synthesize_rag`, `execute_system_command`, `system_task` | 🟢 Low (Standard operations) |
| **`The_Architect`** | `charon/agents/architect.py` | Task & State Control | `rescind_order`, `cancel_action`, `update_state` | 🟢 Low (State management) |
| **`The_Scout`** | `charon/agents/scout/agent.py` | Web Reconnaissance | `search_web`, `scrape_page_content` | 🟢 Low (Read-only web queries) |
| **`The_Engineer`** | `charon/agents/engineer/agent.py` | Dynamic Code & Repair | `solve_edge_case`, `generate_script`, `run_existing_script`, `solve_coding_task`, `execute_sandbox_code` | 🔴 High (Approval on `execute_sandbox_code` / `run_existing_script`) |
| **`The_Overseer`** | `charon/agents/overseer/agent.py` | System Maintenance | `optimize_databases`, `audit_vector_store`, `prune_logs_and_cache`, `prune_orphaned_assets`, `get_system_health`, `run_full_maintenance` | 🟡 Medium (Approval on destructive purges) |
| **`The_Steward`** | `charon/agents/steward/agent.py` | Smart Lab & IoT | `control_appliance`, `publish_mqtt`, `read_sensor_net`, `discover_devices` | 🔴 High (Approval on thermal/relay hardware control) |

---

## 2. Safety Intercept Classification

The Charon daemon enforces a strict three-tier safety framework determined by the `requires_approval` property on incoming agent intent payloads:

* 🔴 **High Intercept (Gatekeeper Guardrail):** Operations that modify physical disk root structures, execute un-audited code subshells, or command potentially dangerous thermal/relay hardware. Execution is frozen immediately, and the daemon enters `awaiting_gatekeeper` state until an operator sends `proceed` or `cancel`.
* 🟡 **Medium Intercept (Operator Confirmation):** Operations involving hardware flashing, g-code transmission to active fabrication machinery, or permanent vector memory/database record deletions.
* 🟢 **Low / Auto-Execution:** Read-only queries, analytical blueprinting, workspace scaffolding, non-destructive file writes, and background telemetry.

---

## 3. Universal Schema Inheritance

All agent request payloads inherit from `BaseAgentPayload` to ensure standardized parameter parsing and passive background memory collection:


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/archivist.md`

```markdown
# Agent Card: `The_Archivist`

**File Path:** `docs/architecture/agents/archivist.md`

**Operational Domain:** Vector Memory Management, RAG Retrieval, PDF Datasheet Knowledge Base & System Rule Persistence

**Target Module:** `charon/agents/archivist/agent.py`

**Safety Intercept Level:** 🟡 Medium (Approval required for record/rule deletion)

---

## 1. Overview & Action Summary

`The_Archivist` manages persistent vector memory using ChromaDB persistent storage (`chroma.sqlite3`). It maintains two isolated collections to separate high-level system rules and preferences from dense technical PDF datasheet knowledge, handling deduplication, sliding-window chunking, cross-collection RAG fallbacks, and multi-pass record expungement.

### Target Actions

| Action Enum | Description | Intercept Guardrail |
| --- | --- | --- |
| `search_ledger` | Queries stored system rules, user preferences, and fact vectors | 🟢 Read-only |
| `store_record` / `record_rule` | Deduplicates and commits new rules or facts to vector store | 🟢 Non-destructive write |
| `expunge_record` / `delete_rule` | Permanently removes vector records via literal or semantic matching | 🟡 Requires Operator Approval |
| `summarize_ledger` | Aggregates and lists stored system rules and facts | 🟢 Read-only |
| `index_datasheet` / `index_pdf` | Extracts, chunks, and indexes technical PDF datasheets | 🟢 Non-destructive write |
| `search_datasheets` / `query_datasheet` | Performs semantic vector search against indexed datasheet knowledge | 🟢 Read-only |

---

## 2. Agent Architecture


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/cleaner.md`

```markdown
# Agent Card: `The_Cleaner`

**File Path:** `docs/architecture/agents/cleaner.md`

**Operational Domain:** Workspace Hygiene, Directory Maintenance, CAD Iteration Sweeping & Log Retention

**Target Module:** `charon/agents/cleaner/agent.py`

**Safety Intercept Level:** 🔴 High (Approval required for `delete_project_workspace`)

---

## 1. Overview & Action Summary

`The_Cleaner` serves as Charon’s primary workspace hygiene and directory maintenance agent. It enforces clean structure across CAD revisions, cleans historical rotated logs, scaffolds standardized mechatronics workspaces, and executes workspace purges under multi-layered boundary safety protocols.

### Target Actions

| Action Enum | Description | Intercept Guardrail |
| --- | --- | --- |
| `initialize_project_workspace` | Scaffolds directory structure for new mechatronics projects | 🟢 Auto-executes |
| `commit_workspace` | Captures or commits current workspace state / snapshots | 🟢 Auto-executes |
| `sweep_cad_iterations` | Identifies and archives deprecated CAD version files | 🟢 Auto-executes |
| `list_workspaces` | Enumerates active project directories in the workspace | 🟢 Read-only |
| `prune_logs` | Cleans rotated log streams past their age limit | 🟢 Auto-executes |
| `delete_project_workspace` | Permanently purges a project directory and its artifacts | 🔴 Requires Operator Approval |

---

## 2. Agent Architecture


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/engineer.md`

```markdown
# Agent Card: `The_Engineer`

**File Path:** `docs/architecture/agents/engineer.md`

**Operational Domain:** Dynamic Code Generation, Self-Healing Repair & Subshell Sandbox Execution

**Target Module:** `charon/agents/engineer/agent.py`

**Safety Intercept Level:** 🔴 High (Approval required for `execute_sandbox_code` and `run_existing_script`)

---

## 1. Overview & Action Summary

`The_Engineer` is Charon’s dynamic code generation, self-healing bug resolution, and subshell sandbox execution agent. It transforms high-level objective specifications into verified, runnable Python scripts, iteratively fixing runtime errors and auditing disk output artifacts using Python’s Abstract Syntax Tree (AST).

### Target Actions

| Action Enum | Description | Intercept Guardrail |
| --- | --- | --- |
| `solve_edge_case` | Main self-healing feedback loop for complex objectives | 🟢 Auto-executes within sandbox |
| `generate_script` | Synthesizes Python script files without direct execution | 🟢 Non-destructive write |
| `run_existing_script` | Executes an existing script on disk via subshell | 🔴 Requires Operator Approval |
| `solve_coding_task` | Standalone coding task execution and verification | 🟢 Auto-executes within sandbox |
| `execute_sandbox_code` | Executes arbitrary dynamic code directly in subshell | 🔴 Requires Operator Approval |

---

## 2. Agent Architecture


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/machinist.md`

```markdown
# Agent Card: `The_Machinist` (The Fabrication Bridge)

**File Path:** `docs/architecture/agents/machinist.md`

**Target Module:** `charon/agents/machinist/agent.py`

**Agent Class:** `TheMachinist`

**Agent Enum:** `AgentEnum.The_Machinist`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only CAD/CAM workspace file scanning) / 🟡 **Medium Intercept** (Executing local CAD mesh exports, CAM slicing subprocesses, and transmitting G-code payloads to network hardware endpoints)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Machinist`** acts as Charon’s mechatronic fabrication bridge, connecting digital CAD/CAM design representations to physical 3D printers and CNC hardware endpoints. It manages headless CAD model translation (STEP/SCAD to STL), automated toolpath slicing via local CLI engines (PrusaSlicer, OrcaSlicer, etc.), project fabrication artifact indexing, and direct HTTP network delivery of G-code payloads to networked fabrication controllers (OctoPrint, Klipper/Moonraker).

Designed with strong fallback resilience, `The_Machinist` handles missing local CAD/CAM binaries through dry-run simulation mode and gracefully stages toolpath files on local disk when hardware endpoints are offline.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`MachinistPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `export_cad_to_stl`, `export_stl`, `stl`, `convert_cad` | `_export_cad_to_stl` | `source_file`, `cad_file`, `file`, `input_file`, `output_path`, `dry_run` | Converts parametric CAD files (`.step`, `.scad`, `.fcstd`) into 3D mesh (`.stl`) files via OpenSCAD or FreeCADcmd. |
| `generate_gcode`, `slice`, `slicing`, `gcode` | `_generate_gcode` | `stl_file`, `geometry_file`, `source_file`, `file`, `profile`, `layer_height`, `infill`, `dry_run` | Slices 3D mesh models into machine toolpaths (`.gcode`) using local slicer binaries with custom layer/infill options. |
| `transmit_to_printer`, `transmit`, `print`, `upload_gcode`, `send_to_printer` | `_transmit_to_printer` | `gcode_file`, `file`, `target_file`, `printer_url`, `api_key`, `start_print`, `dry_run` | Uploads `.gcode` binary payloads over HTTP/REST multi-part forms to OctoPrint or Moonraker endpoints. |
| `inspect_cad_files`, `list_cad`, `cad_info`, `scan_cad` | `_inspect_cad_files` | `project_name`, `project_directory`, `base_path` | Recursively indexes CAD, mesh, and G-code assets within project workspaces and reports file sizes in KB. |

---

## 3. Subsystem Logic & Architectural Features

### Multi-Tiered Path Resolution Cascade (`_resolve_file_path`)

`The_Machinist` resolves input targets using a 4-pass heuristic search cascade when prompts lack explicit paths:

1. **Explicit Key Lookup:** Checks parameter dict for matching key aliases (`source_file`, `stl_file`, `gcode_file`, etc.).
2. **Raw Prompt Normalization:** Attempts to parse raw prompt input if dict keys are missing.
3. **Workspace Directory Globbing:** If a project directory name is supplied, `_resolve_file_path` checks a prioritized subdirectory search matrix:

$$\mathcal{D}_{\text{search}} = \{\text{proj\_path}/\text{cad},\; \text{proj\_path}/\text{models},\; \text{proj\_path}/\text{3d},\; \text{proj\_path}\}$$

It evaluates each location against supported extensions ($\mathcal{E}_{\text{target}} \subseteq \{ \text{.stl}, \text{.step}, \text{.stp}, \text{.fcstd}, \text{.scad}, \text{.gcode} \}$) and selects the first match.

4. **Environment Path Resolution:** Resolves absolute/relative paths against `PROJECTS_DIR` and expands user homes (`~/`).

### Headless CAD Translation (`_export_cad_to_stl`)

Converts solid geometry models into tessellated STL meshes:

* **OpenSCAD Engine:** Executes headless script conversions for `.scad` files (`openscad -o <out.stl> <in.scad>`).
* **FreeCAD Engine:** Routes B-Rep solids (`.step`, `.stp`, `.fcstd`) through `FreeCADcmd`.
* **Fallback & Dry-Run Protocol:** If required binaries are absent on system `PATH` or `dry_run=True`, parent directories are created and empty placeholder files are touched to ensure downstream pipeline continuity.

### Headless CAM Toolpath Slicing (`_generate_gcode`)

Dynamically detects slicer binaries on system `PATH` (`prusa-slicer`, `orca-slicer`, `slic3r`, `cura-cli`) and invokes slicing operations:

* **Parameter Mapping:** Translates input variables into CLI flags (`--layer-height`, `--fill-density`, `--load`).
* **Summary Extraction:** Captures CLI output streams to return print time, filament usage, and layer estimations.

### Hardware Transmission Bridge (`_transmit_to_printer`)

Communicates directly with 3D printer controllers (OctoPrint / Moonraker REST APIs) using standard Python `urllib.request`:

* **Native Multi-Part HTTP Encoding:** Constructs raw multi-part `form-data` binary POST requests (`Content-Type: multipart/boundary=----CharonBoundary`) without third-party dependencies.
* **Fault-Tolerant Staging Protocol:** If hardware endpoints are powered off or time out, network errors (`URLError`, `TimeoutError`) are caught gracefully. The agent logs the error and flags the G-code as **staged on local disk** for manual dispatch.

### Workspace Artifact Inspection (`_inspect_cad_files`)

Scans directories recursively for fabrication assets matching signatures $\mathcal{E}_{\text{fab}} = \{ \text{.step}, \text{.stp}, \text{.scad}, \text{.fcstd}, \text{.stl}, \text{.3mf}, \text{.gcode} \}$. Storage sizes are computed as:

$$S_{\text{KB}} = \text{round}\left( \frac{\text{stat().st\_size}}{1024}, 1 \right)$$

---

## 4. Execution Chaining & Integration Example


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/overseer.md`

```markdown
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/planner.md`

```markdown
# Agent Card: `The_Planner` (Strategy & Metacognitive Supervisor)

**File Path:** `docs/architecture/agents/planner.md`

**Target Module:** `charon/agents/planner/agent.py`

**Agent Class:** `ThePlanner`

**Agent Enum:** `AgentEnum.The_Planner`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only analysis, task decomposition, and sequence drafting auto-chain to execution) / 🔴 **High Intercept** (When invoking subshell script execution via `execute_sandbox_code`)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Planner`** functions as Charon's strategist, metacognitive supervisor, and execution architect. It translates broad, high-level user instructions into structured Directed Acyclic Graphs (DAGs) for multi-agent dispatch, drafts comprehensive engineering implementation blueprints, diagnoses complex system/compilation logs during self-healing loops, dynamically resolves workspace paths, and executes dynamic Python code within an isolated subshell sandbox with AST-driven disk artifact verification.

Powered locally by Ollama (`llama3.1`), `The_Planner` acts as the primary cognitive bridge when incoming prompts require decomposition across multiple specialist agents.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`PlannerPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `decompose_task`, `decompose`, `build_dag` | `_decompose_task` | `objective`, `prompt`, `intent` | Decomposes a complex goal into a ordered JSON list of agent actions. |
| `draft_build_sequence`, `plan`, `build_sequence` | `_draft_build_sequence` | `objective`, `prompt`, `intent` | Generates a structured multi-step engineering specification and build plan. Supports token streaming. |
| `analyze_error_logs`, `diagnose` | `_analyze_error_logs` | `log_content`, `logs`, `content` | Parses compilation or runtime stack traces to extract root causes and prescribe immediate fixes. |
| `execute_sandbox_code`, `run_sandbox` | `_execute_sandbox_code` | `prompt`, `intent`, `code` | Synthesizes Python code, executes it inside an isolated subshell, and audits generated file artifacts via AST checks. |

---

## 3. Subsystem Logic & Metacognitive Capabilities

### DAG Task Decomposition (`_decompose_task`)

Transforms unstructured prompts into a sequential multi-agent plan represented as structured JSON.

* **Agent Capabilities Vocabulary:** Prompts the model with strict action/parameter definitions for all 12 Charon agents.
* **Output Validation:** Forces JSON format enforcement (`format="json"`). Strips backtick formatting and validates array structure before passing output downstream to the `OrchestrationEngine`.


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/quartermaster.md`

```markdown
# Agent Card: `The_Quartermaster` (Logistics & Component Documentation)

**File Path:** `docs/architecture/agents/quartermaster.md`

**Target Module:** `charon/agents/quartermaster/agent.py`

**Agent Class:** `TheQuartermaster`

**Agent Enum:** `AgentEnum.The_Quartermaster`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only stock checks & BOM audits) / 🟡 **Medium Intercept** (Database inventory mutation, PDF downloads, and subprocess `curl` fallbacks)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Quartermaster`** serves as Charon's logistics, inventory manager, and component datasheet pipeline. It maintains standard SQLite database ledgers (`quartermaster.db`) to track component stock and physical bin locations, performs automated Bill of Materials (BOM) stock shortage audits against project CSV files, and orchestrates the automated retrieval, database logging, and vector memory indexing of part datasheets.

`The_Quartermaster` integrates directly with **`The_Scout`** for web mirror discovery when primary PDF links fail, and passes downloaded documentation to **`The_Archivist`** for automatic vector chunking and semantic storage in ChromaDB.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`QuartermasterPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `check_inventory`, `inventory`, `check_stock` | `_check_inventory` | `part_number`, `query`, `mpn` | Queries SQLite for part stock levels, assigned storage bins, and linked datasheet paths. |
| `fetch_datasheet`, `get_datasheet`, `download_datasheet` | `_fetch_datasheet` | `part_number`, `url`, `category`, `mpn` | Downloads PDF datasheets via `urllib`/`curl`, records metadata in SQLite, and invokes vector indexing via `The_Archivist`. |
| `log_inventory`, `add_inventory`, `log_part` | `_log_inventory` | `part_number`, `quantity`, `storage_bin`, `category`, `manufacturer`, `description`, `package_footprint` | Upserts part specifications into `parts` and increments stock levels in `inventory`. |
| `generate_bom`, `audit_bom`, `check_bom` | `_generate_bom` | `project_directory` | Parses a project's `bom/assembly_bom.csv` and computes part shortages against current inventory stock. |

---

## 3. Subsystem Logic & Architectural Features

### Conversational MPN Normalization (`_clean_mpn`)

Filters out conversational prompt noise, prompt verbs, and system keywords to extract clean Manufacturer Part Numbers (MPNs):

* **Noise Filtering:** Uses regex to strip terms like `download`, `search`, `datasheet`, `pinout`, `pdf`, `please`, `check`, etc.
* **Token Extraction:** Evaluates alphanumeric candidate tokens ($\ge 3$ characters) and selects the longest contiguous token, returning it in uppercase format (e.g., `"please fetch datasheet for stm32f405rg"` $\rightarrow$ `"STM32F405RG"`).

### Robust PDF Fetch Pipeline (`_download_pdf_bytes`)

Retrieves binary PDF payloads through a two-tiered fetch architecture designed to bypass common anti-bot mechanisms:

1. **Tier 1 (Native `urllib`):** Issues requests using custom browser user-agent and Sec-Fetch headers.
2. **Tier 2 (`curl` Subprocess Fallback):** Executes an isolated `curl` process (`-sSL --compressed --http1.1`) with a strict `--max-time 8` timeout.
3. **Magic Byte Verification:** Verifies that the initial 1024 bytes of the response contain the `%PDF` header (`b"%PDF" in content[:1024]`).

### Multi-Agent Integration Flow


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/scout.md`

```markdown
# Agent Card: `The_Scout` (Web Reconnaissance & Content Extraction)

**File Path:** `docs/architecture/agents/scout.md`

**Target Module:** `charon/agents/scout/agent.py`

**Agent Class:** `TheScout`

**Agent Enum:** `AgentEnum.The_Scout`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only HTTP web searches & URL page content scraping; no local storage mutations, shell calls, or file writes)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Scout`** serves as Charon’s domain-agnostic web reconnaissance agent. It provides web search capabilities, query result parsing, and direct URL page extraction. `The_Scout` converts raw web data into clean, sanitized Markdown and plain-text snippets for context injection and upstream LLM ingestion.

To ensure high availability, `The_Scout` employs a dual-tiered search fallback strategy (DuckDuckGo primary with Google Search fallback) and aggressive domain filtering to ignore layout noise and aggregator bloat. For page scraping, it utilizes `httpx` and `BeautifulSoup` to strip non-content HTML markup (navigation bars, footers, scripts, and forms) before applying character windowing.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`ScoutPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `search_web`, `search`, `web_search`, `query_web`, `google_search` | `_search_web` | `query`, `prompt`, `raw_prompt`, `max_results` | Executes a web search query across primary/secondary search engines, filters domain noise, and returns formatted Markdown search results. |
| `scrape_page_content`, `scrape`, `fetch_url`, `scrape_url`, `read_page`, `fetch` | `_scrape_url` | `url`, `link`, `max_chars` | Fetches an HTTP/HTTPS endpoint, decomposes non-content DOM elements, normalizes whitespace, and truncates text to `max_chars`. |

---

## 3. Subsystem Logic & Architectural Features

### Query Cleaning & Regex Normalization (`_clean_query`)

Before issuing network requests, query strings are cleaned to remove wrapping LLM artifacts, quotes, or Markdown syntax:


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/spark.md`

```markdown
# Agent Card: `The_Spark` (Electrical Engineering & Firmware Automation)

**File Path:** `docs/architecture/agents/spark.md`

**Target Module:** `charon/agents/spark/agent.py`

**Agent Class:** `TheSpark`

**Agent Enum:** `AgentEnum.The_Spark`

**Safety Intercept Level:** 🔴 **High Intercept** (Flashing microcontroller hardware over physical USB/serial buses) / 🟡 **Medium Intercept** (Executing CLI compilation processes and writing PCB production artifacts to disk)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Spark`** functions as Charon’s electrical engineering and embedded firmware specialist. It bridges high-level hardware design specifications with physical hardware realization. The agent automates EDA tasks using `kicad-cli` (Gerber fabrication plotting, NC drill generation, and Bill of Materials exports) and manages embedded firmware lifecycles using PlatformIO (`pio`).

`The_Spark` includes automated workspace discovery for nested embedded directory structures (`/firmware`) and PCB files (`.kicad_pcb`), gracefully falling back to simulation mode when underlying CLI dependencies are missing or when executing dry runs.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`SparkPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `compile_firmware`, `compile`, `build`, `build_firmware` | `_compile_firmware` | `project_directory`, `project_name`, `environment`, `dry_run` | Compiles embedded firmware source code via PlatformIO (`pio run`) for specified build environments. |
| `flash_hardware`, `flash`, `upload`, `upload_firmware` | `_flash_hardware` | `project_directory`, `project_name`, `port`, `environment`, `dry_run` | Uploads compiled binary payloads to target microcontrollers via USB/Serial ports using PlatformIO (`pio run -t upload`). |
| `export_gerbers`, `gerbers`, `export_pcb`, `plot_gerbers` | `_export_gerbers` | `pcb_file`, `project_directory`, `dry_run` | Plots production Gerber layers and NC drill files (`.drl`) using `kicad-cli pcb export`. |
| `export_bom`, `generate_bom`, `bom` | `_export_bom` | `pcb_file`, `project_directory`, `dry_run` | Generates a Bill of Materials (`_bom.csv`) from the corresponding KiCad schematic (`.kicad_sch`) using `kicad-cli sch export bom`. |

---

## 3. Subsystem Logic & Architectural Features

### Target Project Resolution Cascade (`_resolve_project_dir`)

When resolving project workspace paths from explicit parameters or raw prompt strings, `The_Spark` executes a search cascade:

1. **Explicit Parameter Extraction:** Inspects `project_directory`, `project_path`, `project_name`, or `base_path`.
2. **Token Extraction:** Strips conversational text artifacts from raw prompts when parameter dictionaries are unpopulated.
3. **Workspace Path Resolution:** Checks absolute/user-expanded local paths (`~/`) before evaluating default system workspace locations (`PROJECTS_DIR / <target_str>`).
4. **Nested PlatformIO Detection:** If `<target_path>/firmware/platformio.ini` is present, `The_Spark` automatically updates the active working directory:

$$\text{Path}_{\text{active}} = \begin{cases} \text{Path}_{\text{target}}/\text{firmware} & \text{if } (\text{Path}_{\text{target}}/\text{firmware}/\text{platformio.ini}).\text{exists}() \\ \text{Path}_{\text{target}} & \text{otherwise} \end{cases}$$

### Automated PCB File Discovery (`_find_pcb_file`)

If no explicit `pcb_file` parameter is passed, `The_Spark` performs structured searches across candidate directories in priority order:

$$\mathcal{S}_{\text{pcb}} = \{\text{target\_path}/\text{cad},\; \text{target\_path}/\text{hardware},\; \text{target\_path}\}$$

The agent evaluates each directory using glob pattern matching (`*.kicad_pcb`) and selects the first matching design file.

### Firmware Build & Flash Pipelines (`_compile_firmware`, `_flash_hardware`)

* **Subprocess Execution:** Wraps `pio run` and `pio run --target upload` commands, forwarding targeted build environments (`-e <env>`) and hardware upload interfaces (`--upload-port <port>`).
* **Console Log Windowing:** CLI output streams $O$ are captured and trimmed to prevent memory overload:

$$O_{\text{trimmed}} = \begin{cases} O & \text{if } \vert{}O\vert{} \le 500 \\ O[-500:] & \text{if } \vert{}O\vert{} > 500 \end{cases}$$

* **Simulation Fallback:** If `pio` is absent on system `PATH` or `dry_run=True`, operations execute in simulated dry-run mode.

### KiCad EDA Generation Pipeline (`_export_gerbers`, `_export_bom`)

Automates board production exports via `kicad-cli`:

* **Gerber & Drill Generation:** Executes dual-pass exports creating both fabrication layer plots and NC drill files in `<pcb_dir>/gerbers/`.
* **BOM Export:** Maps the PCB file stem to its matching schematic (`<pcb_stem>.kicad_sch`) and exports structured CSV hardware manifests to `<pcb_dir>/bom/`.

---

## 4. Execution Chaining & Integration Example


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/architecture/agents/steward.md`

```markdown
# Agent Card: `The_Steward` (Home Automation & IoT Control)

**File Path:** `docs/architecture/agents/steward.md`

**Target Module:** `charon/agents/steward/agent.py`

**Agent Class:** `TheSteward` (Alias: `StewardAgent`)

**Agent Enum:** `AgentEnum.The_Steward`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only sensor queries and device state discovery) / 🟡 **Medium Intercept** (Toggling home appliances, executing service calls, and publishing telemetry to MQTT brokers)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Steward`** serves as Charon’s physical environment bridge, managing Home Automation networks, IoT sensor networks, and physical state controls. It provides direct REST API integration with Home Assistant and raw TCP/IP messaging capabilities over MQTT.

Through `The_Steward`, Charon can monitor physical laboratory/workspace environments (e.g., temperature, power consumption, relay status), trigger automated equipment power states, and publish raw telemetry payloads to remote microcontrollers or edge brokers.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`StewardPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `control_appliance`, `control`, `set_state`, `toggle` | `control_appliance` | `target_device`, `entity_id`, `device`, `command`, `service`, `payload`, `data` | Calls Home Assistant domain services (`turn_on`, `turn_off`, `toggle`) for a specific target entity (`domain.entity_id`). |
| `publish_mqtt`, `mqtt`, `publish` | `publish_mqtt` | `topic`, `mqtt_topic`, `payload`, `data`, `message` | Transmits raw text or serialized JSON payloads to an MQTT broker channel via `paho-mqtt`. |
| `read_sensor_net`, `read_sensor`, `get_state`, `read` | `read_sensor_net` | `target_device`, `entity_id`, `device` | Reads state telemetry and attributes for a specified entity. Calls `discover_devices()` if target is omitted. |
| `discover_devices`, `discover`, `list_devices` | `discover_devices` | None | Queries Home Assistant for all active entities and returns a summary list with states and friendly names. |

---

## 3. Subsystem Logic & Architectural Features

### Environment Configuration & Initialization

`The_Steward` automatically configures API endpoints and broker options via environment variables:

* **Home Assistant REST URL:** `HOMEASSISTANT_URL` (Defaults to `[http://homeassistant.local:8123](http://homeassistant.local:8123)`).
* **Long-Lived Access Token:** `HOMEASSISTANT_TOKEN` (Required for HTTP Authorization headers).
* **MQTT Connection Settings:** `MQTT_BROKER_HOST` (default: `localhost`), `MQTT_BROKER_PORT` (default: `1883`), `MQTT_USER`, and `MQTT_PASSWORD`.

### Home Assistant REST Interface (`_make_ha_request`)

All REST API interactions use standard library `urllib.request` with strict 10-second connection timeouts and Bearer Token authentication headers:


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/design/dynamic_skill_ecosystem_spec.md`

```markdown
# CHARON — Technical Design Specification
## Dynamic Skill Checkout & PartVault Sync Ecosystem

**Storage Path**: `docs/design/dynamic_skill_ecosystem_spec.md`  
**System Target**: Charon Daemon v0.1.0+ (`charond`)  
**Status**: Approved / Sprint Architecture Spec  
**Author**: Charon Engineering  

---

## 1.0 System Architecture & Context

This document provides the complete technical specification, Pydantic schemas, SQL queries, and execution flow diagrams for the **Dynamic Skill & Sync Ecosystem**. 

The architecture operates on a **Hybrid File-Source + SQLite Index** pattern with strict database domain isolation:
1. **Templates on Disk:** Skills are authored as clean disk templates (`manifest.json` + `plugin.py`) located in `charon/skills/dynamic/`, `charon/skills/staged/`, or `~/.local/share/charon/skills/`.
2. **Ingestion Engine:** At startup or on file events, the `SkillIngestionEngine` scans disk templates, validates Pydantic schemas, verifies binary dependencies (`shutil.which`), and compiles an index into Charon's local database (`~/.local/share/charon/charon.db` -> `skill_registry`).
3. **Sub-Millisecond Checkout:** Specialist agents negotiate capabilities via sub-millisecond SQLite queries before dynamically importing executable plugin modules via `importlib`.
4. **Automated Staging Pipeline:** Unfulfilled capability requests logged by agents trigger auto-synthesis of `SkillBlueprint` specifications in `charon/skills/staged/` once a gap threshold ($\ge 3$) is reached.
5. **Isolated PartVault Sync:** PartVault operations remain strictly isolated within `~/.local/share/partvault/partvault.db` (`system_metadata`), queried exclusively by `The_Quartermaster` agent over IPC/REST APIs.

### 1.1 Database Domain & XDG Path Allocation

* **Charon Local DB (`~/.local/share/charon/charon.db`):** Owned by `charond`. Holds `skill_registry`, `skill_gaps`, and `blackboard_state`.
* **PartVault DB (`~/.local/share/partvault/partvault.db`):** Owned by PartVault / `The_Quartermaster`. Holds `system_metadata` and `parts_catalog`.
* **Skill Disk Storage:** `charon/skills/dynamic/`, `charon/skills/staged/`, and `~/.local/share/charon/skills/`.

### 1.2 High-Level Capability, Ingestion & Checkout Flow

```mermaid
sequenceDiagram
    autonumber
    participant Disk as Staged / Dynamic Disk
    participant Ingest as SkillIngestionEngine
    participant DB as Charon SQLite (charon.db)
    participant Engine as Orchestration Engine
    participant Agent as BaseAgent
    participant Librarian as SkillLibrarian
    participant Blackboard as TaskBlackboard
    participant GapReg as SkillGapRegistry
    participant Bus as TelemetryBus

    Note over Disk, DB: Phase A: Startup / Staging Ingestion
    Ingest->>Disk: Scan manifest.json & plugin.py
    Ingest->>Ingest: Validate SkillManifest Pydantic Schema
    Ingest->>DB: Upsert into skill_registry table

    Note over Engine, Bus: Phase B: Capability Evaluation & Dynamic Checkout
    Engine->>Agent: evaluate_capability(target_action, params)
    
    alt Action is Native
        Agent-->>Engine: ContractResponse(READY, capability_type="native")
    else Action is Dynamic / Missing
        Agent->>Librarian: is_skill_available(target_action, agent_name)
        Librarian->>DB: SELECT shelf_tags, system_requirements FROM skill_registry
        
        alt Skill Indexed & System Reqs Met
            DB-->>Librarian: Match Found & Binaries Verified
            Librarian-->>Agent: True
            Agent-->>Engine: ContractResponse(READY, capability_type="dynamic_skill")
            Engine->>Agent: execute(action, params)
            Agent->>Librarian: checkout_skill(action, agent_name)
            Librarian->>Disk: importlib load plugin.py
            Librarian-->>Agent: Loaded Dynamic Callable
            Agent->>Bus: emit("skill_checked_out", skill_id)
            Agent->>Agent: Execute Dynamic Callable
        else Skill Missing or System Reqs Failed
            Librarian-->>Agent: False
            Agent-->>Engine: ContractResponse(UNSUPPORTED_ACTION)
            Engine->>Blackboard: record_unfulfilled_requirement(action)
            Engine->>GapReg: log_gap(action, agent_name, context)
            GapReg->>Bus: emit("skill_checkout_failed", action)
            opt Gap Threshold Exceeded (>= 3)
                GapReg->>Disk: Write blueprint template to charon/skills/staged/
                GapReg->>Ingest: Trigger Staging Sync
            end
        end
    end
```

---

## 2.0 Component Technical Specifications

### 2.1 Task 1: Core Skill Model & Hybrid Librarian
**Target File**: `charon/core/skills.py`

#### 2.1.1 Pydantic Manifest Schema (`SkillManifest`)
```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class SkillManifest(BaseModel):
    """Schema governing dynamic skill plugin manifests (manifest.json)."""
    skill_id: str = Field(..., description="Unique skill identifier, e.g. 'kicad_autoroute'")
    shelf_tags: List[str] = Field(
        default_factory=list, 
        description="Target agent names or wildcards, e.g. ['The_Spark', 'The_Engineer'] or ['*']"
    )
    supported_actions: Dict[str, str] = Field(
        ..., 
        description="Map of supported action keys to python entry point methods, e.g. {'autoroute_board': 'run_freerouting'}"
    )
    system_requirements: List[str] = Field(
        default_factory=list, 
        description="Required CLI binaries or system utilities, e.g. ['kicad-cli', 'java']"
    )
    consumed_artifacts: List[str] = Field(default_factory=list, description="Expected input file extensions/types")
    produced_artifacts: List[str] = Field(default_factory=list, description="Generated output file extensions/types")
```

#### 2.1.2 Hybrid DB Lookup & Dynamic Module Execution (`SkillLibrarian`)
```python
import importlib.util
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Charon.Core.Skills")

class SkillLibrarian:
    """Central authorization desk and execution switch backed by SQLite indexing."""
    
    def __init__(self, db_conn: sqlite3.Connection):
        self.db = db_conn

    def is_skill_available(self, action: str, agent_name: str) -> bool:
        """Queries local SQLite skill_registry for instant shelf-tag and binary health verification."""
        cursor = self.db.execute(
            "SELECT shelf_tags, system_requirements FROM skill_registry WHERE action_name = ? AND is_active = 1",
            (action,)
        )
        row = cursor.fetchone()
        if not row:
            return False

        shelf_tags = json.loads(row["shelf_tags"])
        system_requirements = json.loads(row["system_requirements"])

        # Shelf-tag authorization check
        if "*" not in shelf_tags and agent_name not in shelf_tags:
            logger.warning(f"[LIBRARIAN] Agent '{agent_name}' unauthorized for skill '{action}'.")
            return False

        # System requirement binary check
        return all(shutil.which(req) is not None for req in system_requirements)

    def checkout_skill(self, action: str, agent_name: str) -> Optional[Callable]:
        """Validates authorization and imports physical module from indexed file path."""
        if not self.is_skill_available(action, agent_name):
            return None

        cursor = self.db.execute(
            "SELECT skill_id, entry_file_path, handler_name FROM skill_registry WHERE action_name = ?",
            (action,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        entry_path = Path(row["entry_file_path"])
        if not entry_path.exists():
            logger.error(f"[LIBRARIAN] File missing for skill '{row['skill_id']}' at {entry_path}")
            return None

        spec = importlib.util.spec_from_file_location(
            f"charon.skills.dynamic.{row['skill_id']}", 
            entry_path
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, row["handler_name"], None)
```

---

### 2.2 Task 2: Agent Determinant Evaluation & Capability Negotiation
**Target File**: `charon/agents/base.py`

#### 2.2.1 Capability Probing & Dynamic Execution Switch (`BaseAgent`)
```python
from enum import Enum
import shutil
import asyncio
from typing import Any, Dict, Optional, List
from pydantic import BaseModel

class CapabilityType(str, Enum):
    NATIVE = "native"
    DYNAMIC_SKILL = "dynamic_skill"
    UNSUPPORTED = "unsupported"

class ContractResponse(BaseModel):
    status: str
    capability_type: CapabilityType
    missing_prerequisites: List[str] = []

class BaseAgent:
    name: str = "BaseAgent"
    supported_actions: List[str] = []
    system_requirements: List[str] = []
    librarian: Optional[Any] = None

    def evaluate_capability(self, target_action: str, params: Optional[Dict[str, Any]] = None) -> ContractResponse:
        # 1. Native Determinant Check
        if target_action in self.supported_actions:
            missing_reqs = [req for req in self.system_requirements if shutil.which(req) is None]
            if missing_reqs:
                return ContractResponse(
                    status="CAPABILITY_GAP",
                    capability_type=CapabilityType.NATIVE,
                    missing_prerequisites=missing_reqs
                )
            return ContractResponse(status="READY", capability_type=CapabilityType.NATIVE)

        # 2. Dynamic Librarian Checkout Check
        if self.librarian and self.librarian.is_skill_available(target_action, agent_name=self.name):
            return ContractResponse(status="READY", capability_type=CapabilityType.DYNAMIC_SKILL)

        return ContractResponse(status="UNSUPPORTED_ACTION", capability_type=CapabilityType.UNSUPPORTED)

    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        # Native method execution
        if hasattr(self, action) and callable(getattr(self, action)):
            method = getattr(self, action)
            if asyncio.iscoroutinefunction(method):
                return await method(params)
            return method(params)

        # Dynamic skill execution
        if self.librarian:
            skill_handler = self.librarian.checkout_skill(action, agent_name=self.name)
            if skill_handler:
                if asyncio.iscoroutinefunction(skill_handler):
                    return await skill_handler(self, params)
                return skill_handler(self, params)

        raise NotImplementedError(f"Action '{action}' is not executable by {self.name}.")
```

---

### 2.3 Task 3: Skill Ingestion Engine & Database Index
**Target File**: `charon/core/skills_ingestion.py`

#### 2.3.1 SQLite Schema (`charon.db`)
```sql
CREATE TABLE IF NOT EXISTS skill_registry (
    action_name TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    shelf_tags TEXT NOT NULL,          -- JSON array e.g. '["The_Spark", "The_Engineer"]'
    system_requirements TEXT NOT NULL, -- JSON array e.g. '["kicad-cli"]'
    entry_file_path TEXT NOT NULL,    -- Absolute path to plugin.py
    handler_name TEXT NOT NULL,       -- Method name inside plugin.py
    is_active INTEGER DEFAULT 1,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2.3.2 Template Ingestion Engine (`SkillIngestionEngine`)
```python
import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional
from charon.core.skills import SkillManifest

logger = logging.getLogger("Charon.Core.Ingestion")

class SkillIngestionEngine:
    """Scans disk templates, validates Pydantic schemas, and compiles index entries into SQLite."""

    def __init__(self, db_conn: sqlite3.Connection, search_paths: Optional[List[Path]] = None):
        self.db = db_conn
        self.search_paths = search_paths or [
            Path("charon/skills/dynamic"),
            Path("charon/skills/staged"),
            Path.home() / ".local/share/charon/skills"
        ]

    def sync_disk_to_db(self) -> int:
        """Scans disk manifests and compiles them into the SQLite skill_registry table."""
        indexed_count = 0
        
        for search_path in self.search_paths:
            expanded = search_path.expanduser().resolve()
            if not expanded.exists():
                continue

            for manifest_path in expanded.rglob("manifest.json"):
                try:
                    manifest = SkillManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
                    skill_dir = manifest_path.parent
                    entry_file = skill_dir / "plugin.py"

                    if not entry_file.exists():
                        logger.warning(f"Plugin code missing at {entry_file}, skipping ingestion.")
                        continue

                    for action_name, handler_name in manifest.supported_actions.items():
                        self.db.execute(
                            """
                            INSERT INTO skill_registry 
                            (action_name, skill_id, shelf_tags, system_requirements, entry_file_path, handler_name, is_active, indexed_at)
                            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                            ON CONFLICT(action_name) DO UPDATE SET
                                skill_id = excluded.skill_id,
                                shelf_tags = excluded.shelf_tags,
                                system_requirements = excluded.system_requirements,
                                entry_file_path = excluded.entry_file_path,
                                handler_name = excluded.handler_name,
                                is_active = 1,
                                indexed_at = CURRENT_TIMESTAMP;
                            """,
                            (
                                action_name,
                                manifest.skill_id,
                                json.dumps(manifest.shelf_tags),
                                json.dumps(manifest.system_requirements),
                                str(entry_file.resolve()),
                                handler_name,
                            )
                        )
                        indexed_count += 1
                except Exception as e:
                    logger.error(f"Failed to ingest manifest at {manifest_path}: {e}")

        self.db.commit()
        logger.info(f"[INGESTION] Successfully indexed {indexed_count} actions into SQLite skill_registry.")
        return indexed_count
```

---

### 2.4 Task 4: Automated Staging Pipeline & Gap Registry
**Target Files**: `charon/core/gap_registry.py`, `charon/core/coordinator/orchestrator.py`

When an agent reports `UNSUPPORTED_ACTION`, the coordinator routes the gap to `SkillGapRegistry`. When a gap count reaches threshold ($\ge 3$), the system auto-synthesizes blueprint templates into `charon/skills/staged/<action_name>/`.

#### 2.4.1 Gap Logging & Coordinator Escalation
```python
async def dispatch_task(self, action_name: str, payload: dict):
    contract = agent.evaluate_capability(action_name)
    
    if contract.status == "READY":
        return await agent.execute(action_name, payload)
        
    self.blackboard.record_unfulfilled_requirement(
        action=action_name,
        agent=agent.name,
        missing_reqs=contract.missing_prerequisites
    )
    
    blueprint = self.gap_registry.log_gap(
        action_name=action_name,
        agent_name=agent.name,
        context=payload
    )
    
    await self.telemetry_bus.broadcast({
        "event_type": "skill_checkout_failed",
        "action": action_name,
        "agent": agent.name,
        "blueprint_created": blueprint is not None
    })
```

---

### 2.5 Task 5: PartVault Database Metadata & Sync Protocol
**Target Files**: `partvault/db.py`, `charon/agents/quartermaster/agent.py`

PartVault maintains key-value sync metadata inside its isolated SQLite database at `~/.local/share/partvault/partvault.db`.

#### 2.5.1 Key-Value Schema & Upsert SQL
```sql
CREATE TABLE IF NOT EXISTS system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO system_metadata (key, value, updated_at)
VALUES ('last_synced_at', :sync_time, CURRENT_TIMESTAMP)
ON CONFLICT(key) DO UPDATE SET
    value = excluded.value,
    updated_at = CURRENT_TIMESTAMP;
```

---

## 3.0 Verification & Testing Suite Specs

| Test Module | Coverage Objective | Target Mock / Assertion |
| :--- | :--- | :--- |
| `tests/test_skill_ingestion.py` | Verify disk template compilation to SQLite | Ingest sample manifest; assert row creation in `skill_registry`. |
| `tests/test_skill_checkout.py` | Verify SQLite lookup & dynamic import | Assert `checkout_skill()` queries DB and loads/executes dynamic `plugin.py`. |
| `tests/test_gap_registry.py` | Verify capability gap auto-staging | Log 3 gaps; verify staged template creation in `charon/skills/staged/`. |
| `tests/test_partvault_sync.py` | Verify atomic SQLite metadata writes | Perform concurrent reads during WAL-mode `system_metadata` upserts on `partvault.db`. |

---

## 4.0 Associated Developer Specifications

- **`docs/PLUGINS.md`**: Guide for authoring dynamic skills, writing `manifest.json`, and defining shelf tags.
- **`docs/PARTVAULT_SYNC.md`**: Protocol specification for SQLite WAL key-value synchronization and REST force-sync endpoints.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/guides/CLI_REFERENCE_MANUAL.md`

```markdown
## Charon CLI Reference Manual

### Overview & Architecture

Charon features a modular CLI architecture. Top-level commands route directly to sub-tools (`librarian`, `forge`, `telemetry`), while standard command strings initiate the Concierge Agent prompt loop.

### 1. Skill Librarian (`charon librarian` / `charon-librarian`)

Manage skill authorizations (`shelf_tags`), inspect dynamic/staged skills, run manifest schema checks, and promote verified staged skills.

- **List All Discovered Skills & Permissions:**
  
  Bash
  
  ```
  charon librarian list
  ```
  
- **Grant Agent Authorization:**
  
  Bash
  
  ```
  charon librarian grant extract_pdf_ocr_skill The_Archivist
  ```
  
- **Revoke Agent Authorization:**
  
  Bash
  
  ```
  charon librarian revoke extract_pdf_ocr_skill The_Engineer
  ```
  
- **Promote Staged Skill to Production Dynamic Directory:**
  
  Bash
  
  ```
  charon librarian promote hallucinated_vector_pruning_action_skill
  ```
  
- **Validate Manifest Integrity & Auto-Fix Legacy Schemas:**
  
  Bash
  
  ```
  charon librarian check --fix
  ```
  
- **Re-Index Disk Manifests into SQLite (`charon_state.db`):**
  
  Bash
  
  ```
  charon librarian sync
  ```
  

### 2. Skill Forge CLI (`charon forge` / `charon-forge`)

Analyze skill gaps logged when agents attempt unsupported actions, and scaffold dynamic Python skill plugins.

- **List Open Skill Gaps Logged in Database:**
  
  Bash
  
  ```
  charon forge list
  ```
  
- **Resolve Skill Gap by ID:**
  
  Bash
  
  ```
  charon forge resolve --gap-id 2 --action extract_pdf_ocr --agent The_Engineer
  ```
  
- **Interactive Skill Synthesis Wizard:**
  
  Bash
  
  ```
  charon forge
  ```
  

### 3. Telemetry Trace Viewer (`charon telemetry`)

Inspect real-time execution events, prompt traces, and system bus logs.

- **Launch Telemetry TUI:**
  
  Bash
  
  ```
  charon telemetry
  ```
  

### 4. Interactive Concierge Client (`charon`)

Run real-time tasks with the Charon agent fleet.

- **Start Interactive REPL:**
  
  Bash
  
  ```
  charon
  ```
  
- **Execute Non-Interactive Command & Exit Immediately:**
  
  Bash
  
  ```
  charon "Export KiCad schematic BOM for rev_b.kicad_sch" -n
  ```
  
- **Bypass Router & Force Direct Agent Dispatch:**
  
  Bash
  
  ```
  charon "Inspect vector store indexes" -a The_Archivist
  ```
  
- **Check Daemon Connectivity:**
  
  Bash
  
  ```
  charon --ping
  ```
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/guides/SYSTEM_VERSIONING_AND_TESTING.md`

```markdown
# Charon: Versioning, Artifact Management & Testing Architecture

## 1. Overview

This document specifies Charon's code binding, version tracking, artifact isolation, and automated release pipeline. It guarantees that test runs, generated logs, and system outputs are deterministically tied to exact Git commits, global Semantic Versions, and individual file revisions.

---

## 2. Versioning Architecture

### Single Source of Truth

* **`charon/__version__.py`**: Contains system-level `__version__ = "X.Y.Z"`.
* **`../../pyproject.toml`**: Configured with `dynamic = ["version"]` via setuptools attribute resolution referencing `charon.__version__.__version__`.

### Runtime Resolution (`../../charon/core/version.py`)

At runtime, Charon dynamically inspects the environment via Git subprocess calls:

* **Commit SHA**: Short 7-character Git hash (`git rev-parse --short HEAD`).
* **Branch**: Current checked-out branch (`git rev-parse --abbrev-ref HEAD`).
* **Dirty Flag**: Boolean indicator tracking uncommitted changes (`git status --porcelain`).
* **Version String Format**: `vX.Y.Z-g<commit_sha> (dirty)`

### Dual-Version File Headers

To prevent AI code generation or localized module updates from triggering unintended project-wide major/minor version bumps, every Python module in `../../charon` maintains a dual-version header docstring:


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `docs/planning/PLANNING.md`

```markdown
# CHARON — Active Planning & Roadmap

**Current Sprint Authority for OpenCode (Planning Mode).** Refer to `docs/architecture/00_system_overview.md` for tech stack rules and runtime invariants.

---

## 🎯 Active Sprint: Dynamic Skill Ecosystem & PartVault Sync
*Technical Specification:* [`docs/design/dynamic_skill_ecosystem_spec.md`](../design/dynamic_skill_ecosystem_spec.md)

### Architectural Invariants
* **Hybrid File-Source + SQLite Index:** Dynamic skills are authored as disk templates (`manifest.json` + `plugin.py`) in `charon/skills/dynamic/`, `charon/skills/staged/`, or `~/.local/share/charon/skills/`. The `SkillIngestionEngine` scans and compiles these into an indexed `skill_registry` table in `charon_state.db` for sub-millisecond capability lookups.
* **Strict Database Isolation:** Charon state (`charon_state.db`, `charon_ledger.db`, `chroma_db/`) remains completely decoupled from PartVault state (`partvault.db`). PartVault access is governed exclusively through `The_Quartermaster` agent over REST/IPC.
* **Automated Gap Staging:** Capability gaps logged by agents persist to `skill_gaps` in `charon_state.db`. When an unfulfilled action reaches threshold ($\ge 3$), blueprint templates are auto-synthesized in `charon/skills/staged/` for non-blocking code generation.

---

## 📋 Sprint Checklist & Task Breakdown

### Task 1: Skill Librarian Shelf-Tag Indexing & Plugin Registry (`charon/core/skills.py`)
- [ ] **1.1 Standardize Skill Manifest Schema (`SkillManifest`)**:
  - Define a structured Pydantic v2 model containing: `skill_id`, `shelf_tags` (e.g., `["The_Spark", "The_Engineer"]` or `["*"]`), `supported_actions`, `system_requirements` (CLI binaries/libraries), `consumed_artifacts`, and `produced_artifacts`.
- [ ] **1.2 Implement Hybrid Shelf-Tag Lookup (`SkillLibrarian.is_skill_available` / `list_available_actions`)**:
  - Perform sub-millisecond SQLite queries against `skill_registry` in `charon_state.db` matching calling agent shelf-tags and binary prerequisites (`shutil.which`).
- [ ] **1.3 Dynamic Skill Checkout Routine (`SkillLibrarian.checkout_skill`)**:
  - Implement dynamic module loading via `importlib.util.spec_from_file_location` using indexed file paths retrieved from `skill_registry`.
  - Return an executable callable bound to the calling agent instance upon checkout.

### Task 2: Agent Determinant Evaluation & Capability Negotiation (`charon/agents/base.py`)
- [ ] **2.1 Refine Determinant Evaluation (`BaseAgent.evaluate_capability`)**:
  - **Native Determinant Check**: Evaluate internal `supported_actions` and system requirements.
  - **Librarian Checkout Check**: Query `self.librarian.is_skill_available()` if native check fails.
  - Return a `ContractResponse` indicating whether the skill is native, checked out dynamically, or missing.
- [ ] **2.2 Dynamic Execution Dispatch Switch (`BaseAgent.execute`)**:
  - Dispatch execution to checked-out dynamic skill handlers from `SkillLibrarian` when target actions are not in native routing tables.
- [ ] **2.3 Prerequisite & System Requirement Health Probe**:
  - Run system dependency probes (`shutil.which`) prior to approving skill checkout, failing gracefully if prerequisites are missing.

### Task 3: Skill Ingestion Engine & Database Indexing (`charon/core/skills_ingestion.py`)
- [ ] **3.1 Ingestion Engine Implementation (`SkillIngestionEngine`)**:
  - Build scanning loop across search paths (`charon/skills/dynamic`, `charon/skills/staged`, and `~/.local/share/charon/skills`).
  - Validate Pydantic `SkillManifest` files and upsert entries into `skill_registry` table in `charon_state.db`.
- [ ] **3.2 Pre-Turn Capability Query in Orchestration Dispatch (`charon/core/coordinator/`)**:
  - Wire `OrchestrationEngine` / `AgentDispatcher` to invoke `evaluate_capability()` during contract negotiation prior to task execution.
- [ ] **3.3 Telemetry & Event Bus Logging (`charon/telemetry/`)**:
  - Emit live WebSocket telemetry traces (`skill_checked_out`, `skill_checkout_failed`) over `TelemetryBus` to render live skill adoption in the Terminal HUD.

### Task 4: Gap Escalation, Auto-Staging & Skill Forge CLI (`charon/core/gap_registry.py`, `charon/cli/main.py`, `charon/skill_forge_cli.py`)
- [ ] **4.1 Gap Tracking & Auto-Staging Synthesizer (`charon/core/gap_registry.py`)**:
  - Log `UnfulfilledRequirement` entries to `skill_gaps` table in `charon_state.db`.
  - Automatically synthesize blueprint template files (`manifest.json` & `plugin.py` stubs) into `charon/skills/staged/<action_name>/` when gap threshold $\ge 3$ is reached.
- [ ] **4.2 Register Subcommand in Core CLI Parser (`charon/cli/main.py`)**:
  - Add `forge` (alias `skill-forge`) to CLI subcommands alongside `telemetry` and `daemon`.
  - Support optional flags: `--action <action_name>` and `--blueprint-id <id>`.
- [ ] **4.3 Implement Skill Forge CLI Launcher & SDK Polling**:
  - Dynamically import and invoke `charon.skill_forge_cli.main()`, supporting both synchronous and coroutine execution patterns via `asyncio.get_running_loop()`.
  - Use `CharonSDK` / `CharonClient` to query pending blueprints (`/v1/skills/blueprints`) directly from `charond` and render interactive Rich terminal prompts for staging code review.
- [ ] **4.4 Global Console Script Registration (`pyproject.toml`)**:
  - Ensure `charon-forge = "charon.skill_forge_cli:main"` is registered under `[project.scripts]`.

### Task 5: PartVault Database Metadata & Sync Protocol (`partvault/db.py`, `quartermaster/`, `charon/gateway/routes.py`)
- [ ] **5.1 Schema Initialization & Migration (`partvault/db.py`)**:
  - Initialize isolated key-value metadata table in `partvault.db`:  
    `CREATE TABLE IF NOT EXISTS system_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);`.
- [ ] **5.2 Daemon Sync Upsert & WebSocket Telemetry Emission**:
  - Implement atomic upserts in `The_Quartermaster` (`INSERT ... ON CONFLICT(key) DO UPDATE ...`).
  - Broadcast `database_synced` event over `TelemetryBus` upon sync completion.
- [ ] **5.3 SDK / RPC Endpoints (`charon/gateway/routes.py`)**:
  - Implement `GET /v1/system/sync-status` returning key-value states.
  - Implement `POST /v1/system/force-sync` for UI-triggered reconciliation.

### Task 6: Verification, Testing & Documentation
- [ ] **6.1 Ingestion & SQLite Registry Index Test (`tests/test_skill_ingestion.py`)**:
  - Ingest sample disk manifests; assert proper compilation into `charon_state.db -> skill_registry`.
- [ ] **6.2 End-to-End Dynamic Skill Checkout Test (`tests/test_skill_checkout.py`)**:
  - Simulate an unequipped agent requesting non-native actions, verifying dynamic SQLite lookup and module execution.
- [ ] **6.3 Skill Blueprint & Gap Registry Integration Test (`tests/test_gap_registry.py`)**:
  - Test gap logging and threshold-based auto-staging generation in `charon/skills/staged/`.
- [ ] **6.4 Skill Forge CLI Test (`tests/test_skill_forge.py`)**:
  - Verify `$ charon forge` queries daemon blueprints and outputs valid plugin structures.
- [ ] **6.5 PartVault Sync Metadata Test (`tests/test_partvault_sync.py`)**:
  - Assert concurrent reading during atomic `system_metadata` upserts under SQLite WAL mode on `partvault.db`.
- [ ] **6.6 Plugin & Sync Developer Specification (`docs/PLUGINS.md` & `docs/PARTVAULT_SYNC.md`)**:
  - Document plugin creation standards (`manifest.json`, shelf tags) and PartVault sync endpoints.

---

## 🗄️ XDG Persistence & Database Architecture Matrix

### Charon Runtime Domain (`~/.local/share/charon/`)
| File / Directory | Engine / Type | Table / Purpose |
| :--- | :--- | :--- |
| `charon_state.db` | SQLite (WAL) | **Engine State**: `skill_registry`, `skill_gaps`, `blackboard_state`, active task contracts. |
| `charon_ledger.db` | SQLite (WAL) | **Audit & Telemetry**: Token usage logs, cost tracking, historical task execution audits. |
| `chroma_db/` | Chroma Vector Store | **Semantic Memory**: Context embeddings and vector index (`chroma.sqlite3` + binary HNSW graphs). |
| `skills/` | File Directory | **Dynamic Skill Storage**: User-installed dynamic skills (`manifest.json` + `plugin.py`). |
| `workspaces/` | Directory Tree | **Task Sandboxes**: Ephemeral workspaces per task run (`task_<id>/`). |

### PartVault Inventory Domain (`~/.local/share/partvault/`)
| File / Directory | Engine / Type | Table / Purpose |
| :--- | :--- | :--- |
| `partvault.db` | SQLite (WAL) | **Quartermaster Domain**: `system_metadata` key-value sync table & inventory catalog tables. |

---

## 📋 Medium & Long-Term Roadmap

### Phase 1: Infrastructure Scaling & Gateway Consolidation
- **FastAPI Entrypoint Consolidation**: Merge legacy test gateway app (`charon.gateway.main.app`) and daemon app (`charon.daemon:app`) into a unified application entry point.
- **Distributed Task Queue**: Evaluate replacing the single-threaded queue in `charon/daemon.py` with an async job broker (Redis Streams or NATS) for heavy CAD/EDA compilation tasks.

### Phase 2: Database & Memory Scaling
- **PostgreSQL Migration**: Prepare `quartermaster.db` migration path from embedded SQLite to PostgreSQL for concurrent multi-client writes.
- **ChromaDB Client-Server**: Transition ChromaDB from local file mode to server instance for shared multi-process vector access.

---

## 📜 Completed Milestones

- ✅ **Transport Migration**: Deprecated legacy D-Bus in favor of FastAPI + WebSockets daemon on port 8000.
- ✅ **Agent Fleet Gateway**: Implemented PEP 562 lazy loading in `charon/agents/__init__.py`.
- ✅ **Interactive CLI & Telemetry Viewer**: Built interactive terminal REPL (`charon`) and real-time trace viewer (`charon telemetry`).
- ✅ **Pydantic v2 Intent Engine**: Built structured request validation and self-healing fallback loops.
- ✅ **Spec Drift Alignment**: Fully synchronized file paths, action enums, and safety matrices across all 10 agent cards and master core specs.
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "charon"
dynamic = ["version"]
description = "Autonomous Mechatronics & Hardware Engineering Assistant Engine"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "chromadb",
    "pypdf",
    "pydantic",
    "pygobject-stubs>=2.17.0",
    "httpx",
    "websockets",
    "prompt-toolkit",
    "rich",
    "fastapi>=0.141.1",
    "uvicorn>=0.51.0",
    "ollama>=0.6.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.23.0",
]

[project.scripts]
charon = "charon.cli.main:main"
charon-cli = "charon.cli.main:main"
charon-forge = "charon.skill_forge_cli:main"
charon-librarian = "charon.cli.librarian:main"
charond = "charon.daemon:main"

[tool.setuptools.dynamic]
version = {attr = "charon.__version__.__version__"}

[tool.setuptools.packages.find]
where = ["."]

# =========================================================================
# PYTEST CONFIGURATION
# =========================================================================
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = "-v --cov=charon --cov-report=term-missing --cov-report=html"
asyncio_mode = "strict"

# =========================================================================
# COVERAGE CONFIGURATION
# =========================================================================
[tool.coverage.run]
branch = true
source = ["charon"]
omit = [
    "tests/*",
    "*/site-packages/*",
    "*/__init__.py",
]

[tool.coverage.report]
show_missing = true
precision = 2
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if __name__ == .__main__.:",
    "raise AssertionError",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
    "@overload",
]

[tool.coverage.html]
directory = "htmlcov"

[tool.coverage.xml]
output = "coverage.xml"

```

────────────────────────────────────────────────────────────────────────────────

