### Dev Journal Subsystem

**Purpose**
The Dev Journal serves as the human-in-the-loop workspace for architectural planning, task tracking, and documentation review. It integrates human project management with automated agent workflows.

**Architecture Controller**
The `DevJournal.tsx` component orchestrates this module, managing local state (`activeSubTab`) to navigate between the `DevLogForm` (formerly Scratchpad), the `IssueTracker`, and the `DocQueue`.