"""
charon/agents/generalist/prompts.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: System Prompts, Action Maps, and Detection Patterns for The Generalist.
"""

CONTINENTAL_GENERALIST_PROMPT = (
    "You are Charon, the discreet, unflappable, and articulate Concierge of The Continental mechatronics system.\n"
    "Your tone is polite, concise, professional, slightly formal, and discreet at all times.\n"
    "NEVER use generic AI assistant filler, eager enthusiasm, or pleasantries "
    "(e.g., NEVER say 'I'm glad you think so!', 'How can I help you today?', 'As an AI language model...').\n"
    "Respond to queries with precise clarity and understated elegance. "
    "If confirming a statement or preference, acknowledge it briefly and remain completely in character."
)

RAG_SYNTHESIS_PROMPT = (
    "You are Charon, the discreet, unflappable, and articulate Concierge of The Continental mechatronics system.\n"
    "Your objective is to synthesize retrieved datasheet and ledger context into an elegantly structured, highly legible response.\n"
    "Maintain a polite, formal, and precise tone.\n"
    "Organize technical specifications, pinouts, electrical characteristics, or memory records using clear Markdown headers, "
    "bullet lists, or formatted tables where appropriate.\n"
    "If the retrieved context lacks specific details required to answer the query fully, state what is known and gracefully "
    "note the limitation without speculative filler."
)

SYSTEM_ACTION_PATTERNS = [
    r"\bvolume\b",
    r"\bmute\b",
    r"\bunmute\b",
    r"\bbrightness\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bkill\b",
    r"\bpkill\b",
    r"\bwifi\b",
    r"\bbluetooth\b",
    r"\bsystemctl\b",
    r"\buptime\b",
    r"\bdisk\s+space\b",
    r"\bdf\b",
    r"\bfree\b",
]

# Safeguard patterns that indicate document opening, GUI viewing, or file discovery
PLANNER_HANDOFF_PATTERNS = [
    r"\bpdf\b",
    r"\bdatasheet\b",
    r"\bpapers\b",
    r"\bevince\b",
    r"\bokular\b",
    r"\blibreoffice\b",
    r"\bopen\s+.*?\.(pdf|doc|docx|epub|txt)\b",
    r"\bread\s+.*?\.(pdf|doc|docx)\b",
    r"\bview\s+.*?\.(pdf|doc|docx)\b",
]

VALID_GENERALIST_ACTIONS = (
    "answer_query",
    "synthesize_rag",
    "calculate_math",
    "system_info",
    "execute_system_command",
    "acknowledge",
)

ACTION_MAP = {
    "answer_query": "answer_query",
    "query": "answer_query",
    "ask": "answer_query",
    "chat": "answer_query",
    "respond": "answer_query",
    "synthesize_rag": "synthesize_rag",
    "rag_synthesis": "synthesize_rag",
    "synthesize": "synthesize_rag",
    "rag": "synthesize_rag",
    "calculate_math": "calculate_math",
    "math": "calculate_math",
    "calculate": "calculate_math",
    "compute": "calculate_math",
    "system_info": "system_info",
    "sys_info": "system_info",
    "system_status": "system_info",
    "inspect_os": "system_info",
    "system_task": "execute_system_command",
    "os_task": "execute_system_command",
    "run_cmd": "execute_system_command",
    "execute_command": "execute_system_command",
    "execute_system_command": "execute_system_command",
    "acknowledge": "acknowledge",
    "ack": "acknowledge",
    "note": "acknowledge",
}

KNOWN_CLI_EXECUTABLES = [
    "pactl",
    "amixer",
    "wpctl",
    "systemctl",
    "free",
    "df",
    "ls",
    "ps",
    "echo",
    "cat",
    "git",
    "curl",
    "wget",
    "pkill",
    "kill",
]