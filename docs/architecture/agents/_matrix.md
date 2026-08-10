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

