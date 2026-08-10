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