The Concierge subsystem emits proactive next-step proposals to the frontend UI following execution loop completion. This document covers event payload schemas, stream lifecycle management, and UI presentation specifications.

## Event Payload Schema

Proposals arrive over the `CharonStream` WebSocket channel via the `emit_concierge` handler.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `event_type` | `string` | Yes | Fixed discriminator string `"ConciergeProposalEvent"`. |
| `task_id` | `string` | Yes | UUID of the parent execution lifecycle task. |
| `phrase` | `string` | Yes | Display text for the UI action chip (e.g., *"Draft API Unit Tests"*). |
| `completed_action` | `string` | Yes | Context tag identifying the trigger source (e.g., `"coordinator_loop"`). |
| `suggested_prompt` | `string` | Yes | Full text prompt automatically populated into the input bar upon click. |
| `routing_hint` | `object` | No | Target agent mapping parameters for downstream execution. |

## TypeScript Definitions

```typescript
export interface ConciergeProposalPayload {
  eventType: 'ConciergeProposalEvent';
  taskId: string;
  phrase: string;
  completedAction: string;
  suggestedPrompt: string;
  routingHint?: Record<string, unknown>;
  timestamp: string;
}

export interface ConciergeState {
  activeProposals: ConciergeProposalPayload[];
  isEvaluating: boolean;
  lastProposalId: string | null;
}
```

## UI Component Lifecycle

- **Ingress**: `CharonStream` listener intercepts `emit_concierge` payloads, validates the payload against `ConciergeProposalPayload`, and pushes valid instances to the store.

- **Rendering**: Proposal chips mount inside the active execution response container directly below the primary message bubble.

- **Selection**: Clicking a chip pre-fills the chat prompt textarea with `suggestedPrompt`, highlights routing tags if present, and sets focus to the submit control.

- **Tear-down**: Proposals auto-dismiss whenever the user submits a new prompt, clears the session thread, or manually closes the suggestion bar.

```

<ElicitationsGroup message="What would you like to do next?">
<Elicitation label="Draft React component for Concierge proposal chips" query="Draft React component for Concierge proposal chips" query_intent="CLICKABLE_SUGGESTION" />
<Elicitation label="Add TypeScript WebSocket event handlers for CharonStream" query="Add TypeScript WebSocket event handlers for CharonStream" query_intent="CLICKABLE_SUGGESTION" />
<Elicitation label="Write Cypress end-to-end tests for proposal interactions" query="Write Cypress end-to-end tests for proposal interactions" query_intent="CLICKABLE_SUGGESTION" />
</ElicitationsGroup>
```