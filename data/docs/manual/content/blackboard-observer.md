### BlackboardObserver Architecture

**Data Flow & Subscriptions**
The `BlackboardObserver` acts as the telemetry aggregator. On mount, it establishes two concurrent subscriptions via `wsClient`:
* **`step`**: High-level execution transitions (e.g., phase changes, task handoffs). Appended to the `steps` state.
* **`thought_record`**: Granular Chain-of-Thought (CoT) internal reasoning from the agent fleet. Appended to the `thoughts` state.

It features a split-pane layout, passing the respective state arrays down to `DagVisualizer` (left pane) and `BlackboardTrace` (right pane) for rendering.