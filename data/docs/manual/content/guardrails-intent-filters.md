The guardrail system acts as a strict logical barrier between raw model outputs and desktop actions.

## Proposal Schemas (`schemas.py`)

* **Pydantic Validation:** Formats and verifies structured JSON proposals before executing system or editor modifications.
* **Execution Safety:** Ensures parameters match expected systemic bounds before dispatching.

## Deduplication & Suppression (`constants.py`)

* **Levenshtein Deduplication:** Measures similarity across proposed briefings to prevent repetitive notifications.
* **Chat Suppression:** Evaluates shell activity via regex to suppress proactive popups during routine command execution (e.g., `uptime`, `ls`, `git status`) or active exit flows.