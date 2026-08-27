### Agent Studio Subsystem

**Purpose**
The Agent Studio serves as the primary control surface for fine-tuning the agent fleet. It allows operators to dynamically adjust agent routing priorities, toggle specific capabilities (tools/skills), and hot-reload core system instructions.

**Architecture Controller**
The top-level `AgentStudio.tsx` orchestrator manages the layout and sub-routing using local state (`activeSubTab`). It provides the unified header and handles switching between the `SkillMatrix` and `PromptEditor` views.