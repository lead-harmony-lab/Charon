The orchestration layer coordinates Charon's background activity, task evaluation, and proactive interaction loops.

## Biological Clock & Polling

* **Non-Blocking Execution:** Runs asynchronous temporal polling loops (`scheduler.py`) to monitor system events without blocking the main event loop.
* **Idle Maintenance:** Automatically schedules low-priority optimization tasks during periods of system inactivity.

## Briefing Engine (`core.py`)

* **Session Warmth Tracking:** Calculates session warmth based on recent activity deltas.
* **Ledger Evaluation:** Evaluates completed agent ledger items to assemble concise progress summaries.
* **Proactive Engagement:** Triggers contextual briefings when key milestones or background events complete.