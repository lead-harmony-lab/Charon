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

