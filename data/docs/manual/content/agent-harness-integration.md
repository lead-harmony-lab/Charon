The Concierge subsystem hooks directly into the `OrchestrationEngine` to perform post-execution evaluation and drive proactive UI proposals following prompt completion.

## Interaction Lifecycle

| Stage | Action | Component / Method | Description |
| :--- | :--- | :--- | :--- |
| **1. Ingress** | Event Broadcast | `emitter.emit_system_event` | Emits `TaskDispatchedEvent` payload to signal the UI of active execution. |
| **2. Execution** | Zero-Trust Loop | `Coordinator.run_task_lifecycle` | Runs task planning and tool execution across registered agent roles. |
| **3. Unwrapping** | Result Extraction | `TaskBlackboard._get_results_payload` | Resolves the primary execution payload from SQLite state storage. |
| **4. Broadcast** | Native Output | `emitter.emit_agent_response` | Delivers the raw execution result directly to the client interface. |
| **5. Evaluation** | Proactive Hook | `concierge.evaluate_next_step` | Analyzes execution results and blackboard state to generate next-step proposals. |
| **6. Dispatch** | Proposal Delivery | `emitter.emit_concierge` | Transmits structured proposal payloads to the UI for user review. |

## Proactive Evaluation Payload Interface

During Stage 5, `OrchestrationEngine.process_request` passes five key context variables into `concierge.evaluate_next_step`:

* **`user_query`**: The raw text prompt submitted by the user.
* **`completed_action`**: Fixed identifier set to `"coordinator_loop"`.
* **`execution_result`**: Stringified model dump of the final returned execution object.
* **`blackboard_artifacts`**: Complete raw JSON payload of the blackboard state history.

If the Concierge yields a valid proposal, the resulting object is validated and emitted directly to the UI layer via `emit_concierge`. Failure during Concierge evaluation logs a non-fatal warning, leaving the core execution response intact.