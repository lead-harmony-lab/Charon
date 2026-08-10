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

