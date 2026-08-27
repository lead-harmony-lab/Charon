### AdrViewer.tsx Architecture

**Scope & Information Taxonomy**
Architectural Decision Records (ADRs) document individual, significant design choices, trade-offs, and historical context. Use ADRs to answer *why* a technical path or constraint was chosen over alternatives.

**Technical Implementation**
* **State & Filter Engine**: Tracks loaded records, active document ID, and search queries. Client-side filtering searches across `title`, `id`, `summary`, and raw `content`.
* **REST Synchronization**: Performs initial GET requests to `/v1/docs/adrs` via `authFetch`. Updates existing records using `PUT` calls to `/v1/docs/adrs/:id` with automatic list refreshes on success.
* **Dual View/Edit Workflow**: Displays status badges (`ACCEPTED`, `PROPOSED`, `DEPRECATED`), date tags, and rendered markdown via `MarkdownRenderer`. Switches to inline form fields (`title`, `summary`, `content`) during active editing.