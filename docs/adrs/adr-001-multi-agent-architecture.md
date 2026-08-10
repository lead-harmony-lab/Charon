ADR-001: Local Multi-Agent Architecture with Modular PEP 562 Lazy Loading

    Status: Accepted

    Date: 2026-07-30

    Context:
    Monolithic LLM prompts struggle with bloated toolsets and context saturation when managing complex, multi-domain desktop tasks (EDA hardware design, CAD fabrication, OS maintenance, IoT control). Always-on agent frameworks waste substantial system memory when idle on a developer machine.

    Decision:
    Implement a modular multi-agent fleet coordinated by a central Triage Router. Agents are dynamically loaded using PEP 562 lazy-loaded modules, importing heavy libraries (e.g., CAD parsers, web scraping drivers, vector databases) only when an agent is actively invoked.

    Consequences:

        Positive: Drastically reduces charond startup time and idle RAM usage; isolates domain-specific context prompts to specialized agents.

        Negative: Introduces a small first-call latency penalty when an agent module is imported for the first time in a session.
