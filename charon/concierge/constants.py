"""
charon/concierge/constants.py
System Version: v2.2.0

Module: Concierge Constants & Filters
Defines static routing rules, trivial query patterns, and early-exit phrases.
"""

import re
from typing import Set

# Exit phrases that suppress proactive proposals
EXIT_PHRASES: Set[str] = {
    "that will be all", "thanks", "thank you", "done", "stop", "exit",
    "quit", "nothing else", "goodbye", "n/a", "no", "no thanks",
    "all good", "that is all", "that's all",
}

# Loosened regex to catch conversational filler and suppress trivial follow-ups
TRIVIAL_QUERY_PATTERNS = [
    re.compile(
        r".*(display|show|get|check|print|tell me)?\s*(the)?\s*(current)?\s*(system)?\s*(time|date|clock|uptime|whoami|hostname|pwd)\b.*",
        re.IGNORECASE
    ),
]