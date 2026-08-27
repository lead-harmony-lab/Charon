### Skill Matrix

**Data Flow & Real-Time Sync**
The component initially loads the agent registry via REST (`GET /v1/router/agents`). To ensure UI consistency in a multi-client environment, it actively listens for `router_agent_updated` and `router_tool_toggled` events via `wsClient`, forcing a data refresh whenever the backend state changes.

**Mutation Operations**
* **Priority Weights:** Users can adjust routing priority directly on the agent cards. On blur, this triggers a `PUT /v1/router/agents/{agentId}` request to update the weight.
* **Tool Toggling:** Agent skills are grouped by `skill_type`. Checking or unchecking a specific tool triggers a precise `PATCH /v1/router/agents/{agentId}/tools` request, enabling or disabling the capability without reloading the entire agent.