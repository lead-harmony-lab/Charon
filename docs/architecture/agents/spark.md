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

