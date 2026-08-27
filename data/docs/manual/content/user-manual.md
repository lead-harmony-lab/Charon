# Manual Viewer Architecture

### Scope & Information Taxonomy
The User Manual contains operational, component, and architectural documentation. Use manual pages to describe *how* components interact, *where* responsibilities lie, and *how* to extend harness capabilities. Avoid putting versioned API schemas (use System Specs) or design decision logs (use ADRs) here.

### Technical Implementation
* **Tree State & Drag-and-Drop**: Operates on recursive `ManualNode` trees. Handles node repositioning (`before`, `after`, `inside`) with decoupling routines (`removeNode`, `insertNode`) while blocking invalid ancestor drops via `isDescendant`.
* **API Synchronization**: Fetches and persists the JSON manual tree via `/v1/docs/manual` (`GET`/`PUT`). Features explicit error diagnostics parsing raw text prior to JSON evaluation.
* **Inline Management**: Combines live `MarkdownRenderer` rendering with split-view editing and dynamic modal triggers for adding root or child topics.