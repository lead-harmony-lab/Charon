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

