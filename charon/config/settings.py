"""
charon/config/settings.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Environment variables & runtime settings.
"""

import os
from dotenv import load_dotenv
from charon.config.paths import CHARON_ENV_FILE

# Load user-level env file (~/.config/charon/env) into os.environ if present
if CHARON_ENV_FILE.exists():
    load_dotenv(CHARON_ENV_FILE)

# =============================================================================
# API Security Configuration
# =============================================================================
CHARON_API_KEY = os.getenv("CHARON_API_KEY", "charon-secret-key-change-me")
API_KEY_HEADER_NAME = "X-API-Key"

# =============================================================================
# Engine & Model Defaults
# =============================================================================
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_HEAVY_MODEL = os.getenv("CHARON_HEAVY_MODEL", "llama3.1")
DEFAULT_TRIAGE_MODEL = os.getenv("CHARON_TRIAGE_MODEL", "llama3.1")

# =============================================================================
# Concierge Engine Configuration
# =============================================================================
DEFAULT_CONCIERGE_MIN_CONFIDENCE = float(
    os.getenv("CHARON_CONCIERGE_MIN_CONFIDENCE", "0.80")
)
