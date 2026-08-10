Status: Accepted

Date: 2026-07-30

Context:
Not all OS actions carry equal risk. Read-only commands (cat, ls) should execute instantly with zero latency, while actions like modifying system services (systemctl) or executing generated code require human-in-the-loop validation.

Decision:
Implement a GatekeeperManager that evaluates action payloads against a 4-Tier Execution Risk Matrix:

    Level 0 (Read-Only): Auto-executed silently.

    Level 1 (Workspace Write): Auto-executed in $HOME with event logging.

    Level 2 (System Operations): Paused; triggers desktop/WebSocket confirmation dialogs.

    Level 3 (High-Risk/Root): Blocked for manual pass-through.

Consequences:

    Positive: Keeps the user in control of high-impact changes without causing friction on routine read/write queries.

    Negative: Multi-step workflows pause when hitting Level 2 actions until the user responds to the authorization prompt.
