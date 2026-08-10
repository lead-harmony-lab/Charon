Status: Accepted

Date: 2026-07-30

Context:
Complex user directives require coordinating multiple agents sequentially (e.g., Scout scrapes data → Spark generates schematics → Quartermaster verifies inventory). Passing raw conversational context between steps bloats context windows and increases drift.

Decision:
The Planner agent decomposes complex tasks into sequential Directed Acyclic Graph (DAG) plans. Step parameters support dynamic string variable substitution (e.g., $STEP_1_OUTPUT). Step failures trigger a self-healing loop via The Planner (diagnose action) or escalate to The Engineer.

Consequences:

    Positive: Keeps local LLM context windows lean and focused; handles multi-agent workflows; self-corrects transient errors automatically.

    Negative: Multi-step execution adds latency and multiple inference passes per overall request.
