### Prompt Editor

**Data Flow & State**
The component separates loading the agent list from loading the specific prompt. On mount, it fetches the available agent IDs. When the user changes the `selectedAgent` dropdown, a `useEffect` hook triggers a fetch to `GET /v1/router/agents/{selectedAgent}/prompt` to load the current system instructions into the text area.

**Mutation Operations**
* **Prompt Updates:** Clicking 'Save' sends a `PUT` request with the updated `system_prompt` payload to the backend. The UI provides direct, color-coded feedback (Success/Error) based on the REST response status.