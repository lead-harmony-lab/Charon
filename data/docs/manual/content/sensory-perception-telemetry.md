The sensory ingress layer grants Charon live visibility into the developer's immediate working environment.

## Context Sensors (`telemetry.py`)

* **Window & Desktop Monitoring:** Ingests active GNOME window titles, workspace switches, and active application focus.
* **IDE Integration:** Inspects active IDE buffer content, cursor position, and LSP compiler diagnostic errors.
* **Hardware Load Monitoring:** Samples CPU, RAM, and GPU load limits to avoid triggering intensive LLM tasks during high system stress.

## Vector Memory (`memory.py`)

* **ChromaDB Storage:** Persists past interactions, user code styles, and long-term project context.
* **Semantic Retrieval:** Queries relevant historic context based on current IDE active buffers and task prompts.