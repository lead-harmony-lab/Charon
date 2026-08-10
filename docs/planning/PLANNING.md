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