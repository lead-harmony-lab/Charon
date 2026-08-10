Status: Accepted

Date: 2026-07-30

Context:
To be useful as a workstation concierge, Charon must read and modify files on the real host OS. However, running an LLM agent with unrestricted system root access risks accidental system corruption (e.g., hallucinated rm -rf or overwriting /etc). Sandboxing the agent in a virtual machine or container renders host system management useless.

Decision:
Run charond natively on the host as a systemd --user service with kernel-enforced isolation (ProtectSystem=strict). The entire root filesystem (/, /usr, /etc, /var) is bind-mounted as Read-Only, while $HOME, /tmp, and /run/user/%U remain Read-Write.

Consequences:

    Positive: Provides total protection against catastrophic system mutations at the Linux kernel level without requiring VM/Docker overhead or locking the agent out of the user's workspace.

    Negative: Operations modifying system configurations outside $HOME (e.g., apt install) require escalation mechanisms (pkexec or Gatekeeper approvals).
