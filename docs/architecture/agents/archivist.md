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

