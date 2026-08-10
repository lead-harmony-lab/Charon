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

