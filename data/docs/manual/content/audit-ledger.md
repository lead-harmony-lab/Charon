### Audit Ledger Architecture

**Data Flow & State**
Unlike the live telemetry view, the Audit Ledger is REST-driven. On component mount, it triggers an async `authFetch` to `GET /v1/journal/audit` to retrieve historical `AuditEntry` records.

**Technical Details**
* **Client-Side Filtering**: Features an input field bound to a `filter` state. The view dynamically recalculates `filteredLogs` by checking if the filter string exists within the log's `message` or `source` (case-insensitive).
* **Formatting**: Renders a scrollable monospace list with color-coded severity levels (`ERROR` → Red, `WARN` → Yellow, `INFO` → Blue).