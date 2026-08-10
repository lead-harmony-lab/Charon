# Agent Card: `The_Machinist` (The Fabrication Bridge)

**File Path:** `docs/architecture/agents/machinist.md`

**Target Module:** `charon/agents/machinist/agent.py`

**Agent Class:** `TheMachinist`

**Agent Enum:** `AgentEnum.The_Machinist`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only CAD/CAM workspace file scanning) / 🟡 **Medium Intercept** (Executing local CAD mesh exports, CAM slicing subprocesses, and transmitting G-code payloads to network hardware endpoints)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Machinist`** acts as Charon’s mechatronic fabrication bridge, connecting digital CAD/CAM design representations to physical 3D printers and CNC hardware endpoints. It manages headless CAD model translation (STEP/SCAD to STL), automated toolpath slicing via local CLI engines (PrusaSlicer, OrcaSlicer, etc.), project fabrication artifact indexing, and direct HTTP network delivery of G-code payloads to networked fabrication controllers (OctoPrint, Klipper/Moonraker).

Designed with strong fallback resilience, `The_Machinist` handles missing local CAD/CAM binaries through dry-run simulation mode and gracefully stages toolpath files on local disk when hardware endpoints are offline.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`MachinistPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `export_cad_to_stl`, `export_stl`, `stl`, `convert_cad` | `_export_cad_to_stl` | `source_file`, `cad_file`, `file`, `input_file`, `output_path`, `dry_run` | Converts parametric CAD files (`.step`, `.scad`, `.fcstd`) into 3D mesh (`.stl`) files via OpenSCAD or FreeCADcmd. |
| `generate_gcode`, `slice`, `slicing`, `gcode` | `_generate_gcode` | `stl_file`, `geometry_file`, `source_file`, `file`, `profile`, `layer_height`, `infill`, `dry_run` | Slices 3D mesh models into machine toolpaths (`.gcode`) using local slicer binaries with custom layer/infill options. |
| `transmit_to_printer`, `transmit`, `print`, `upload_gcode`, `send_to_printer` | `_transmit_to_printer` | `gcode_file`, `file`, `target_file`, `printer_url`, `api_key`, `start_print`, `dry_run` | Uploads `.gcode` binary payloads over HTTP/REST multi-part forms to OctoPrint or Moonraker endpoints. |
| `inspect_cad_files`, `list_cad`, `cad_info`, `scan_cad` | `_inspect_cad_files` | `project_name`, `project_directory`, `base_path` | Recursively indexes CAD, mesh, and G-code assets within project workspaces and reports file sizes in KB. |

---

## 3. Subsystem Logic & Architectural Features

### Multi-Tiered Path Resolution Cascade (`_resolve_file_path`)

`The_Machinist` resolves input targets using a 4-pass heuristic search cascade when prompts lack explicit paths:

1. **Explicit Key Lookup:** Checks parameter dict for matching key aliases (`source_file`, `stl_file`, `gcode_file`, etc.).
2. **Raw Prompt Normalization:** Attempts to parse raw prompt input if dict keys are missing.
3. **Workspace Directory Globbing:** If a project directory name is supplied, `_resolve_file_path` checks a prioritized subdirectory search matrix:

$$\mathcal{D}_{\text{search}} = \{\text{proj\_path}/\text{cad},\; \text{proj\_path}/\text{models},\; \text{proj\_path}/\text{3d},\; \text{proj\_path}\}$$

It evaluates each location against supported extensions ($\mathcal{E}_{\text{target}} \subseteq \{ \text{.stl}, \text{.step}, \text{.stp}, \text{.fcstd}, \text{.scad}, \text{.gcode} \}$) and selects the first match.

4. **Environment Path Resolution:** Resolves absolute/relative paths against `PROJECTS_DIR` and expands user homes (`~/`).

### Headless CAD Translation (`_export_cad_to_stl`)

Converts solid geometry models into tessellated STL meshes:

* **OpenSCAD Engine:** Executes headless script conversions for `.scad` files (`openscad -o <out.stl> <in.scad>`).
* **FreeCAD Engine:** Routes B-Rep solids (`.step`, `.stp`, `.fcstd`) through `FreeCADcmd`.
* **Fallback & Dry-Run Protocol:** If required binaries are absent on system `PATH` or `dry_run=True`, parent directories are created and empty placeholder files are touched to ensure downstream pipeline continuity.

### Headless CAM Toolpath Slicing (`_generate_gcode`)

Dynamically detects slicer binaries on system `PATH` (`prusa-slicer`, `orca-slicer`, `slic3r`, `cura-cli`) and invokes slicing operations:

* **Parameter Mapping:** Translates input variables into CLI flags (`--layer-height`, `--fill-density`, `--load`).
* **Summary Extraction:** Captures CLI output streams to return print time, filament usage, and layer estimations.

### Hardware Transmission Bridge (`_transmit_to_printer`)

Communicates directly with 3D printer controllers (OctoPrint / Moonraker REST APIs) using standard Python `urllib.request`:

* **Native Multi-Part HTTP Encoding:** Constructs raw multi-part `form-data` binary POST requests (`Content-Type: multipart/boundary=----CharonBoundary`) without third-party dependencies.
* **Fault-Tolerant Staging Protocol:** If hardware endpoints are powered off or time out, network errors (`URLError`, `TimeoutError`) are caught gracefully. The agent logs the error and flags the G-code as **staged on local disk** for manual dispatch.

### Workspace Artifact Inspection (`_inspect_cad_files`)

Scans directories recursively for fabrication assets matching signatures $\mathcal{E}_{\text{fab}} = \{ \text{.step}, \text{.stp}, \text{.scad}, \text{.fcstd}, \text{.stl}, \text{.3mf}, \text{.gcode} \}$. Storage sizes are computed as:

$$S_{\text{KB}} = \text{round}\left( \frac{\text{stat().st\_size}}{1024}, 1 \right)$$

---

## 4. Execution Chaining & Integration Example

