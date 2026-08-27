### SpecsViewer.tsx Architecture

**Scope & Information Taxonomy**
System Specifications detail concrete technical contracts, interface schemas, payload formats, and versioned system behavior. Use Specs to define *what* technical standards and API invariants a subsystem must uphold.

**Technical Implementation**
* **State & Filter Engine**: Manages local specification records, selected active document, and live query string filtering across `name`, `id`, and raw `content`.
* **REST Synchronization**: Fetches system specs via `/v1/docs/specs` (`GET`) and handles updates through `/v1/docs/specs/:id` (`PUT`) using `authFetch`.
* **Dual View/Edit Workflow**: Renders document name, version tags, and markdown content. Swaps display modes to expose raw text inputs for `name`, `version`, and `content` upon edit activation. 