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

