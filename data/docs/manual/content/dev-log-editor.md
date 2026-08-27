### Dev Log Editor

**Scope & Interface**
A sophisticated form engine (`DevLogForm.tsx`) replacing the basic scratchpad, designed for authoring system observations, runbooks, and defect logs with rich metadata.

**Technical Details**
* **Dynamic Autocomplete (`useMentionAutocomplete`)**: Integrates a two-stage querying engine for linking board tickets (trigger: `#`) and Knowledge Base documentation (trigger: `@`, filtering across ADRs, Specs, and dynamically flattened Manual AST nodes).
* **Artifact & Telemetry Linking**: Provides localized input arrays for associating text logs with specific system traces, tickets, or telemetry artifacts.
* **Toolbar & Typography Control**: Utilizes the `DevLogToolbar` to support explicit text-scaling boundaries (discrete font increase/decrease handlers) and visual disabled states for improved readability.
* **Board Integration**: Enables mapping log entries directly to the `IssueTracker` board via `TicketStatus` and `TicketPriority` semantic metadata.