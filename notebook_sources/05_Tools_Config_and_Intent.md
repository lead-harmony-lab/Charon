# Subsystem Domain Context: 05_Tools_Config_and_Intent
> **Generated:** 2026-08-11 06:46 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `Streamline-Dynamic-Routing` | **Commit:** `c416670`

---

## Target File: `charon/config/__init__.py`

```python
"""
charon/config/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Package-level Configuration Entry Point.
Centralizes exports from paths, settings, and logging for clean import syntax
across the Charon application stack.
"""

from charon.config.logging import setup_logging
from charon.config.paths import (
    BASE_DIR,
    CHARON_DATA_DIR,
    CHARON_ENV_FILE,
    CHARON_PKG_DIR,
    CHROMA_DB_DIR,
    DATA_DIR,
    DATASHEET_DIR,
    DATASHEETS_DIR,
    ERROR_LOG_FILE,
    KICAD_DBL_PATH,
    LEDGER_DB_PATH,
    LOGS_DIR,
    MAIN_LOG_FILE,
    PARTVAULT_DATA_DIR,
    PROJECT_LOGS_DIR,
    PROJECT_MEMORY_DIR,
    PROJECTS_DIR,
    QUARTERMASTER_DB_PATH,
    STATE_DB_PATH,
    TASK_QUEUE_DB_PATH,
    USER_CONFIG_DIR,
    XDG_CACHE_HOME,
    XDG_CONFIG_HOME,
    XDG_DATA_HOME,
    XDG_STATE_HOME,
    ensure_ecosystem_directories,
    resolve_project_path,
)
from charon.config.settings import (
    API_KEY_HEADER_NAME,
    CHARON_API_KEY,
    DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    DEFAULT_HEAVY_MODEL,
    DEFAULT_TRIAGE_MODEL,
    OLLAMA_HOST,
)

__all__ = [
    # Logging Configuration
    "setup_logging",
    # XDG Base & Ecosystem Paths
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "USER_CONFIG_DIR",
    "CHARON_ENV_FILE",
    "KICAD_DBL_PATH",
    "CHARON_DATA_DIR",
    "CHARON_PKG_DIR",
    "PROJECT_MEMORY_DIR",
    "CHROMA_DB_DIR",
    "STATE_DB_PATH",
    "LEDGER_DB_PATH",
    "TASK_QUEUE_DB_PATH",
    "PROJECT_LOGS_DIR",
    "LOGS_DIR",
    "MAIN_LOG_FILE",
    "ERROR_LOG_FILE",
    "DATA_DIR",
    "PARTVAULT_DATA_DIR",
    "QUARTERMASTER_DB_PATH",
    "BASE_DIR",
    "PROJECTS_DIR",
    "DATASHEETS_DIR",
    "DATASHEET_DIR",
    "ensure_ecosystem_directories",
    "resolve_project_path",
    # Settings & Environment Constants
    "CHARON_API_KEY",
    "API_KEY_HEADER_NAME",
    "OLLAMA_HOST",
    "DEFAULT_HEAVY_MODEL",
    "DEFAULT_TRIAGE_MODEL",
    "DEFAULT_CONCIERGE_MIN_CONFIDENCE",
]

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/config/logging.py`

```python
"""
charon/config/logging.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: config/logging — Central Logging Configuration for Charon.

Configures dual stream logging: stdout for systemd/journalctl and rotating file handlers
for main daemon events and error isolation.
"""

import logging
from logging.handlers import RotatingFileHandler
import sys

from charon.config.paths import ERROR_LOG_FILE, LOGS_DIR, MAIN_LOG_FILE


def setup_logging(level: int = logging.INFO) -> None:
    """Configures system-wide logging with stdout and rotating file output."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is invoked multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 1. Console Stream Handler (captured by systemd/journalctl)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Main Rotating File Handler (5 MB max, 3 backups)
    main_file_handler = RotatingFileHandler(
        MAIN_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    main_file_handler.setFormatter(formatter)
    main_file_handler.setLevel(logging.INFO)
    root_logger.addHandler(main_file_handler)

    # 3. Dedicated Error File Handler (2 MB max, 2 backups)
    error_file_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    error_file_handler.setFormatter(formatter)
    error_file_handler.setLevel(logging.WARNING)
    root_logger.addHandler(error_file_handler)

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/config/paths.py`

```python
"""
charon/config/paths.py
System Version: v0.1.0 | File Revision: 1.4.0

Module: Application & Ecosystem XDG Path Resolver
Defines canonical XDG-compliant storage paths for Charon background daemon runtime,
logs, state machines, vector stores, dynamic skill registries, task sandboxes, and
external PartVault integrations.
"""

import os
from pathlib import Path
from typing import Union

# =============================================================================
# 0. Repository & Package Base Directories
# =============================================================================
CHARON_PKG_DIR = Path(__file__).resolve().parent.parent  # .../Charon/charon
BASE_DIR = CHARON_PKG_DIR.parent                          # .../Charon

# =============================================================================
# 1. XDG Base Directory Specification Standards
# =============================================================================
XDG_DATA_HOME = Path(
    os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
).resolve()

XDG_CONFIG_HOME = Path(
    os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
).resolve()

XDG_STATE_HOME = Path(
    os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")
).resolve()

XDG_CACHE_HOME = Path(
    os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
).resolve()

# =============================================================================
# 2. Application-Specific XDG Directories & Databases
# =============================================================================
# System Configuration
USER_CONFIG_DIR = XDG_CONFIG_HOME / "charon"
CHARON_ENV_FILE = USER_CONFIG_DIR / "env"
KICAD_DBL_PATH = USER_CONFIG_DIR / "partvault.kicad_dbl"

# Charon Runtime Data & Memory Storage
CHARON_DATA_DIR = XDG_DATA_HOME / "charon"
DATA_DIR = CHARON_DATA_DIR
PROJECT_MEMORY_DIR = CHARON_DATA_DIR / "chroma_db"
CHROMA_DB_DIR = PROJECT_MEMORY_DIR

# Persistent Daemon Databases
STATE_DB_PATH = CHARON_DATA_DIR / "charon_state.db"
LEDGER_DB_PATH = CHARON_DATA_DIR / "charon_ledger.db"
TASK_QUEUE_DB_PATH = STATE_DB_PATH  # Task queue state shares StateManager DB

# Dynamic Skill & Task Sandbox Directories
DYNAMIC_SKILLS_DIR = CHARON_DATA_DIR / "storage"
WORKSPACES_DIR = CHARON_DATA_DIR / "workspaces"

# Repository-Internal Skill Paths (Ingestion & Staging)
PKG_DYNAMIC_SKILLS_DIR = CHARON_PKG_DIR / "storage" / "dynamic"
PKG_STAGED_SKILLS_DIR = CHARON_PKG_DIR / "storage" / "staged"

# Charon Logging & Cache State
PROJECT_LOGS_DIR = XDG_STATE_HOME / "charon" / "logs"
LOGS_DIR = PROJECT_LOGS_DIR
MAIN_LOG_FILE = LOGS_DIR / "charond.log"
ERROR_LOG_FILE = LOGS_DIR / "charond.error.log"

# =============================================================================
# 3. External Integration Directories (PartVault & Workspace)
# =============================================================================
# Shared PartVault Data & Datasheet Storage
PARTVAULT_DATA_DIR = XDG_DATA_HOME / "partvault"
PARTVAULT_DB_PATH = PARTVAULT_DATA_DIR / "partvault.db"
QUARTERMASTER_DB_PATH = PARTVAULT_DB_PATH  # Legacy alias for Quartermaster queries
DATASHEETS_DIR = PARTVAULT_DATA_DIR / "datasheets"
DATASHEET_DIR = DATASHEETS_DIR

# User Workspace Roots
PROJECTS_DIR = Path(
    os.getenv("CHARON_PROJECTS_DIR", Path.home() / "Projects")
).resolve()


def ensure_ecosystem_directories() -> None:
    """Ensures all XDG user directories and workspace runtime folders exist."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CHARON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    PKG_DYNAMIC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    PKG_STAGED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PARTVAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEETS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_project_path(target: Union[str, Path]) -> Path:
    """Resolves a path relative to PROJECTS_DIR if not absolute."""
    path = Path(os.path.expanduser(str(target))).resolve()
    if path.exists():
        return path
    return (PROJECTS_DIR / str(target)).resolve()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/config/settings.py`

```python
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

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/__init__.py`

```python
"""
charon/intent/__init__.py
System Version: v0.1.0 | File Revision: 1.3.0

Top-level intent package interface.
Re-exports core agent enums, manifests, routing models, parser engine, and universal payloads.
"""

from charon.intent.base import (
    BaseAgentPayload,
    MemoryCandidate,
    StrictBaseModel,
)
from charon.intent.manifests import (
    AgentManifest,
    get_agent_manifest,
    get_triage_agent_descriptions,
)
from charon.intent.parser import IntentParser
from charon.intent.payloads.dynamic import DynamicActionPayload
from charon.intent.routing import IntentExtraction, RoutingPayload

__all__ = [
    # Base
    "StrictBaseModel",
    "MemoryCandidate",
    "BaseAgentPayload",
    # Manifests
    "AgentManifest",
    "get_agent_manifest",
    "get_triage_agent_descriptions",
    # Engine
    "IntentParser",
    # Routing
    "RoutingPayload",
    "IntentExtraction",
    # Universal Dynamic Payloads
    "DynamicActionPayload",
]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/base.py`

```python
"""
charon/intent/base.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Foundational Pydantic models and schema helpers.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model enforcing robust parsing against local LLM output variations."""
    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=False,
        populate_by_name=True,
    )


class MemoryCandidate(StrictBaseModel):
    is_persistent: bool = Field(
        default=True,
        description="True if this constitutes a permanent rule, preference, or systemic fact.",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence level of the memory extraction (0.0 to 1.0).",
    )
    fact: str = Field(
        description="The exact preference, rule, or systemic fact to commit to the ledger."
    )


class BaseAgentPayload(StrictBaseModel):
    """Base payload allowing agents to passively capture systemic memories/preferences."""
    memory_candidate: Optional[MemoryCandidate] = Field(
        default=None,
        description="Optional preference/rule extracted during normal execution.",
    )

    @classmethod
    def get_clean_schema(cls) -> Dict[str, Any]:
        """Returns JSON schema with $defs inlined for Ollama structured outputs compatibility."""
        schema = cls.model_json_schema()
        defs = schema.pop("$defs", {})

        def resolve_refs(obj: Any) -> Any:
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            return resolve_refs(defs[def_name])
                return {k: resolve_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_refs(item) for item in obj]
            return obj

        return resolve_refs(schema)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/manifests.py`

```python
"""
charon/intent/manifests.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Agent capability manifests and prompt formatting helpers.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from charon.config.paths import STATE_DB_PATH
from charon.core.skills import SkillLibrarian
from charon.db.repositories import AgentRepository


class AgentManifest(BaseModel):
    """Dynamic metadata representing an agent's capabilities and routing attributes."""
    agent_id: str
    display_name: str
    description: str = ""
    default_action: str = ""
    priority_weight: float = Field(default=1.0, ge=0.0)
    override_triggers: List[str] = Field(default_factory=list)
    active_tools: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    risk_level: int = Field(default=0, ge=0, le=3)


def get_agent_manifest(
    agent_id: str,
    repo: Optional[AgentRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> Optional[AgentManifest]:
    """Retrieves validated agent capabilities using the repository pattern."""
    repo = repo or AgentRepository(db_path)
    agent_data = repo.get_active_agent(agent_id)

    if not agent_data:
        return None

    librarian = SkillLibrarian.get_instance(db_path)

    raw_default = agent_data.get("default_action")
    if raw_default:
        default_action = raw_default
    elif hasattr(librarian, "get_default_action_for_role"):
        default_action = librarian.get_default_action_for_role("system_generalist") or ""
    else:
        default_action = ""

    raw_triggers = agent_data.get("override_triggers", [])
    if isinstance(raw_triggers, str):
        triggers = json.loads(raw_triggers or "[]")
    else:
        triggers = raw_triggers or []

    raw_tools = agent_data.get("active_tools", [])
    if isinstance(raw_tools, str):
        tools = json.loads(raw_tools or "[]")
    else:
        tools = raw_tools or []

    return AgentManifest(
        agent_id=agent_data["agent_id"],
        display_name=agent_data["display_name"],
        description=agent_data.get("description", ""),
        default_action=default_action,
        priority_weight=float(agent_data.get("priority_weight", 1.0)),
        override_triggers=triggers,
        active_tools=tools,
        risk_level=agent_data.get("risk_level", 0),
        is_active=bool(agent_data.get("is_active", 1)),
    )


def get_triage_agent_descriptions(
    repo: Optional[AgentRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """Generates formatted agent capabilities for LLM triage prompts."""
    repo = repo or AgentRepository(db_path)
    librarian = SkillLibrarian.get_instance(db_path)
    lines = []

    active_agents = repo.get_all_active_agents()

    for agent in active_agents:
        agent_id = agent["agent_id"]

        # Delegate dynamic action discovery to the Librarian
        if hasattr(librarian, "list_available_actions"):
            agent_actions = librarian.list_available_actions(agent_id)
        else:
            agent_actions = []

        caps = ", ".join(agent_actions) if agent_actions else "No active dynamic skills"

        lines.append(
            f"- **{agent['display_name']}** (`{agent_id}`): "
            f"{agent.get('description', '')} Capabilities: [{caps}]"
        )

    return "\n".join(lines)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/parser.py`

```python
"""
charon/intent/parser.py
System Version: v0.1.0 | File Revision: 2.2.0

Module: Pass 1 Router Engine evaluating hard shortcuts, per-agent triggers, and priority scaling.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from charon.core.skills import SkillLibrarian
from charon.intent.routing import RoutingPayload
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("Charon.Intent.Parser")


class IntentParser:
    """Evaluates shortcut dispatches, manages dynamic routing rules, and scales LLM triage confidence scores."""

    def __init__(
        self,
        librarian: Optional[SkillLibrarian] = None,
        ollama_client: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ollama_client = ollama_client
        self.extra_config = kwargs

    async def parse(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> RoutingPayload:
        """High-level async intent parsing interface for Orchestrator."""
        shortcut = self.check_hard_shortcuts(prompt)
        if shortcut:
            return RoutingPayload(agent=shortcut)

        return RoutingPayload(agent="coordinator")

    def parse_sync(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> RoutingPayload:
        """High-level sync intent parsing interface for Orchestrator."""
        shortcut = self.check_hard_shortcuts(prompt)
        if shortcut:
            return RoutingPayload(agent=shortcut)

        return RoutingPayload(agent="coordinator")

    def check_hard_shortcuts(self, prompt: str) -> Optional[str]:
        """
        Evaluates user prompts against global route table rules and per-agent trigger keywords.
        Returns target_agent ID if matched, or None.
        """
        clean_prompt = prompt.strip().lower()

        # 1. Check global dynamic routing override rules in RouteRepository
        try:
            override_rules = self.get_override_rules()
            for rule in override_rules:
                trigger = rule.get("trigger", "").lower()
                if clean_prompt.startswith(trigger) or trigger in clean_prompt.split():
                    logger.info(
                        f"[IntentParser] Matched dynamic shortcut: '{trigger}' -> '{rule.get('target_agent')}'"
                    )
                    return rule.get("target_agent")
        except Exception as err:
            logger.warning(
                f"[IntentParser] Dynamic shortcut evaluation error: {err}"
            )

        # 2. Check per-agent trigger words from AgentRepository manifests
        try:
            if hasattr(self.librarian, "agent_repo") and self.librarian.agent_repo:
                manifests = self.librarian.agent_repo.get_all_manifests()
                for agent_id, manifest in manifests.items():
                    for trig in manifest.get("override_triggers", []):
                        if trig.lower() in clean_prompt:
                            logger.info(
                                f"[IntentParser] Matched agent trigger: '{trig}' -> '{agent_id}'"
                            )
                            return agent_id
        except Exception as err:
            logger.warning(
                f"[IntentParser] Could not evaluate agent trigger shortcuts: {err}"
            )

        return None

    def evaluate_and_scale_triage(
        self, prompt: str, raw_llm_scores: Dict[str, float], task_id: Optional[str] = None
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Applies priority multipliers to raw Pass 1 triage scores and emits a TRIAGE_DECISION telemetry trace.

        Formula: Score_final = min(1.0, Score_raw * PriorityWeight)
        """
        manifests = {}
        try:
            if hasattr(self.librarian, "agent_repo") and self.librarian.agent_repo:
                manifests = self.librarian.agent_repo.get_all_manifests()
        except Exception as err:
            logger.warning(
                f"[IntentParser] Could not retrieve agent manifests for triage scaling: {err}"
            )

        weighted_scores: Dict[str, float] = {}

        for agent_id, raw_score in raw_llm_scores.items():
            manifest = manifests.get(agent_id, {})
            weight = float(manifest.get("priority_weight", 1.0))
            final_score = min(1.0, round(raw_score * weight, 4))
            weighted_scores[agent_id] = final_score

        if not weighted_scores:
            selected_agent = "default_agent"
            top_score = 1.0
            weighted_scores = {"default_agent": 1.0}
        else:
            selected_agent = max(weighted_scores, key=weighted_scores.get)
            top_score = weighted_scores[selected_agent]

        # Emit Pass 1 triage decision telemetry trace over TelemetryBus -> WebSockets
        try:
            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.TRIAGE_DECISION,
                    agent_name="IntentParser",
                    action="triage_evaluation",
                    details={
                        "task_id": task_id or "system",
                        "prompt": prompt,
                        "selected_agent": selected_agent,
                        "confidence_score": top_score,
                        "candidate_scores": weighted_scores,
                        "raw_llm_scores": raw_llm_scores,
                    },
                )
            )
        except Exception as err:
            logger.warning(f"[IntentParser] Failed to emit TRIAGE_DECISION trace: {err}")

        return selected_agent, top_score, weighted_scores

    # =========================================================================
    # Dynamic Route Rule Management Delegate Methods
    # =========================================================================

    def get_override_rules(self) -> List[Dict[str, Any]]:
        """Retrieves active global dynamic shortcut override rules."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.get_override_rules()
        return []

    def add_override_rule(self, trigger: str, target_agent: str, description: str = "") -> str:
        """Adds a new shortcut rule into RouteRepository."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.add_override_rule(
                trigger=trigger, target_agent=target_agent, description=description
            )
        raise RuntimeError("RouteRepository not bound to SkillLibrarian.")

    def remove_override_rule(self, rule_id: str) -> bool:
        """Removes a dynamic shortcut rule by rule ID."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.remove_override_rule(rule_id)
        return False
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/payloads/__init__.py`

```python
"""
charon/intent/payloads/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Intent payload schemas package initializer.
Exports universal dynamic payload schema for skill execution.
"""

from charon.intent.payloads.dynamic import DynamicActionPayload

__all__ = [
    "DynamicActionPayload",
]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/payloads/dynamic.py`

```python
"""
charon/intent/payloads/dynamic.py
System Version: v0.1.0 | File Revision: 1.1.0

Universal payload wrapper for dynamic skill execution.
Replaces static compile-time Pydantic models with runtime schema validation.
"""

from typing import Any, Dict
from pydantic import Field

from charon.intent.base import BaseAgentPayload
from charon.core.skills import SkillLibrarian


class DynamicActionPayload(BaseAgentPayload):
    """
    Universal payload for executing any dynamic skill in the registry.
    Bypasses static Pydantic constraints in favor of SQLite schema validation.
    """

    call_action: str = Field(
        ...,
        description="The specific action_name to invoke (e.g., 'list_tasks', 'fetch_datasheet')"
    )
    thought: str = Field(
        default="",
        description="The agent's internal reasoning or plan for calling this tool"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value arguments matching the action's parameter schema"
    )

    def validate_against_manifest(self) -> bool:
        """
        Dynamically checks if required parameters match the JSON Schema stored in the SQLite registry.
        Raises ValueError if required parameters are missing.
        """
        librarian = SkillLibrarian.get_instance()
        action_details = librarian.get_action_details(self.call_action)

        if not action_details:
            default_action = (
                librarian.get_default_action_for_role("system_generalist")
                if hasattr(librarian, "get_default_action_for_role")
                else ""
            )
            # Fallback check for raw conversational routing (no specific tool)
            if default_action and self.call_action == default_action:
                return True
            raise ValueError(f"Action '{self.call_action}' is not indexed in the Librarian.")

        schema_params = action_details.get("parameters", {})
        required_params = schema_params.get("required", [])

        for param in required_params:
            if param not in self.params:
                raise ValueError(
                    f"Missing required parameter '{param}' for action '{self.call_action}'. "
                    f"Expected schema: {schema_params}"
                )

        return True
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/intent/routing.py`

```python
"""
charon/intent/routing.py
System Version: v0.1.0 | File Revision: 1.3.0

Module: First pass routing classification and unified intent extraction schemas.
"""

from typing import Any, Dict, Optional
from pydantic import Field
from charon.intent.base import StrictBaseModel


class RoutingPayload(StrictBaseModel):
    """
    First inference pass: Determine WHO should handle the task.
    Purely analytical classification. No conversational text generation allowed.
    """
    agent: str = Field(
        description="The canonical agent or role identifier (e.g., 'engineer', 'planner', 'generalist') assigned to execute the requested task. Must match an active agent in the system registry."
    )


class IntentExtraction(StrictBaseModel):
    """Unified intent extraction payload returned during orchestrator parsing."""

    agent: str = Field(
        description="The canonical agent or role identifier (e.g., 'engineer', 'planner', 'generalist') assigned to the task."
    )
    action: str = Field(
        description="The dynamic action_name to invoke."
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, description="Extraction confidence score (0.0 to 1.0).")
    raw_prompt: Optional[str] = Field(default=None, description="Original user prompt string.")
    requires_approval: bool = Field(
        default=False, description="Flag indicating if action requires human confirmation via Gatekeeper."
    )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/nodes/workshop_hud.py`

```python
"""
charon/nodes/workshop_hud.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: nodes/workshop_hud.py
Module: Workshop HUD Node for Charon Engine.

Simulates a physical workbench HUD display that renders telemetry,
streams agent execution logs, displays proactive Concierge prompts,
and handles Gatekeeper operator authorization.
"""

import asyncio
import logging
import sys
from typing import Dict, Any

from charon.gateway.models import WSEvent
from charon.sdk import CharonClientNode

# Configure HUD logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("WorkshopHUD")


# ==============================================================================
# Terminal UI Formatting Helpers
# ==============================================================================
def print_banner(title: str, style_char: str = "=") -> None:
    width = 64
    print(f"\n{style_char * width}")
    print(f" {title.center(width - 2)}")
    print(f"{style_char * width}\n")


def print_hud_chip(header: str, content: str, alert_type: str = "INFO") -> None:
    symbols = {"INFO": "ℹ️", "ALERT": "🚨", "PROMPT": "🛎️", "SECURITY": "🛡️"}
    icon = symbols.get(alert_type, "📌")
    print(f"\n┌── {icon} [{header}] ───────────────────────────────────────────┐")
    for line in content.splitlines():
        print(f"│  {line}")
    print("└─────────────────────────────────────────────────────────────┘\n")


# ==============================================================================
# Node Initialization
# ==============================================================================
hud_node = CharonClientNode(
    client_id="workshop_hud_01",
    engine_url="http://localhost:8000",
    default_context={
        "node_type": "heads_up_display",
        "location": "main_workbench",
        "attached_hardware": ["3d_printer_01", "usb_cnc_mill"],
    },
)


# ==============================================================================
# Event Handlers (Targeted Node Bus)
# ==============================================================================
@hud_node.on("agent_log")
async def handle_agent_log(event: WSEvent) -> None:
    """Streams real-time execution logs from active Charon agents."""
    message = event.data.get("message", "")
    sys.stdout.write(message)
    sys.stdout.flush()


@hud_node.on("concierge_suggestion")
async def handle_concierge_suggestion(event: WSEvent) -> None:
    """Renders proactive suggestions evaluated by ConciergeService."""
    phrase = event.data.get("phrase", "")
    suggested_prompt = event.data.get("suggested_prompt", "")
    action_id = event.data.get("id", "unknown")

    formatted_msg = (
        f"{phrase}\n"
        f"► Quick Action [{action_id}]: '{suggested_prompt}'\n"
        f"  (Type 'yes' or 'execute' to accept)"
    )
    print_hud_chip("CONCIERGE PROACTIVE RECOMMENDATION", formatted_msg, alert_type="PROMPT")


@hud_node.on("gatekeeper_intercept")
async def handle_gatekeeper_intercept(event: WSEvent) -> None:
    """Displays safety intercept manifests requiring physical operator sign-off."""
    manifest = event.data.get("manifest", "")
    approval_id = event.data.get("approval_id", "")

    formatted_msg = (
        f"{manifest}\n\n"
        f"► Approval ID: {approval_id}\n"
        f"► Action Required: Reply 'proceed' to execute or 'cancel' to rescind."
    )
    print_hud_chip("GATEKEEPER SECURITY INTERCEPT", formatted_msg, alert_type="SECURITY")


@hud_node.on("task_complete")
async def handle_task_complete(event: WSEvent) -> None:
    """Renders task completion summaries."""
    summary = event.data.get("summary", "")
    print(f"\n✅ [TASK COMPLETE] {summary}\n")


@hud_node.on("overseer_report")
async def handle_overseer_report(event: WSEvent) -> None:
    """Updates HUD status bar with system telemetry."""
    data = event.data
    engine_status = "ONLINE" if data.get("engine_online") else "OFFLINE"
    queue_depth = data.get("queue_depth", 0)
    current_task = data.get("current_task", "Idle")

    # Log telemetry summary on HUD header line
    logger.debug(
        f"[TELEMETRY] Engine: {engine_status} | Queue: {queue_depth} | Active Task: {current_task}"
    )


@hud_node.on("system_alert")
async def handle_system_alert(event: WSEvent) -> None:
    """Renders high-priority broadcast alerts from daemon."""
    severity = event.data.get("severity", "INFO")
    title = event.data.get("title", "SYSTEM NOTICE")
    message = event.data.get("message", "")

    print_hud_chip(f"SYSTEM ALERT - {severity}: {title}", message, alert_type="ALERT")


# ==============================================================================
# Interactive Operator Console
# ==============================================================================
async def operator_input_loop(node: CharonClientNode) -> None:
    """Reads command inputs from the local workstation operator keyboard."""
    await asyncio.sleep(1.0)  # Wait for initial WS connection message
    print_banner("WORKSHOP HUD NODE 01 OPERATIONAL")
    print("Type a prompt or command to dispatch to Charon (e.g., 'compile firmware for project X').")
    print("Type 'exit' or 'quit' to shut down node.\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            # Read input asynchronously from stdin
            user_input = await loop.run_in_executor(None, input, "HUD> ")
            command = user_input.strip()

            if not command:
                continue

            if command.lower() in ["exit", "quit"]:
                logger.info("Shutdown requested by operator.")
                await node.disconnect()
                break

            # Send task to central daemon with client_id attached
            response = await node.submit_task(prompt=command)
            print(f"──► Task dispatched [ID: {response.task_id}] (Agent: {response.assigned_agent or 'Triage'})")

        except Exception as e:
            logger.error(f"Error handling operator input: {e}")
            await asyncio.sleep(0.5)


# ==============================================================================
# Main Entry Point
# ==============================================================================
async def main() -> None:
    # Initialize connection and background WS listener
    await hud_node.connect()

    # Run operator CLI concurrently with WS event listener loop
    try:
        await asyncio.gather(
            hud_node.listen_forever(),
            operator_input_loop(hud_node),
        )
    except asyncio.CancelledError:
        pass
    finally:
        if hud_node.is_connected:
            await hud_node.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWorkshop HUD terminated.")

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/__init__.py`

```python
"""
charon/tools/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package initialization gateway for tools.
"""


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/cad.py`

```python
"""
charon/tools/cad.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless CAD/CAM and Fabrication Tools.

Provides low-level functions for CAD file translation, CAM slicer CLI execution,
and HTTP transmission to 3D printers and CNC hardware.
"""

import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CHAROND.Tools.CAD")


def run_cad_export(
    source_path: Path,
    out_file: Path,
    dry_run: bool = False,
) -> str:
    """Executes a headless CAD converter (OpenSCAD, FreeCADcmd) to export STL geometry."""
    if source_path.suffix.lower() == ".scad" and shutil.which("openscad"):
        cmd = ["openscad", "-o", str(out_file), str(source_path)]
    elif shutil.which("FreeCADcmd"):
        cmd = ["FreeCADcmd", str(source_path), str(out_file)]
    else:
        cmd = None

    if dry_run or not cmd:
        sim_reason = (
            " (Dry Run)"
            if dry_run
            else " (Simulated: No FreeCADcmd/OpenSCAD CLI found)"
        )
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.touch(exist_ok=True)
        return f"Geometric export simulated successfully: {out_file.name}{sim_reason}."

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Successfully exported geometric data to {out_file}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"CAD Export failed: {err_msg}")
        return f"A failure occurred during CAD translation:\n{err_msg}"


def run_slicer(
    slicer_cmd: str,
    stl_path: Path,
    gcode_path: Path,
    profile: Optional[str] = None,
    layer_height: Optional[float] = None,
    infill: Optional[int] = None,
    dry_run: bool = False,
) -> str:
    """Invokes local slicer CLI executable to generate G-Code toolpaths."""
    cmd = [
        slicer_cmd,
        "--export-gcode",
        str(stl_path),
        "--output",
        str(gcode_path),
    ]
    if profile:
        cmd.extend(["--load", str(profile)])
    if layer_height is not None:
        cmd.extend(["--layer-height", str(layer_height)])
    if infill is not None:
        cmd.extend(["--fill-density", f"{infill}%"])

    logger.info(f"Slicing geometry: {stl_path.name} -> {gcode_path.name}")

    slicer_binary = shutil.which(slicer_cmd)
    if dry_run or not slicer_binary:
        sim_reason = (
            " (Dry Run)"
            if dry_run
            else f" (Simulated: Slicer binary '{slicer_cmd}' not found)"
        )
        gcode_path.parent.mkdir(parents=True, exist_ok=True)
        gcode_path.touch(exist_ok=True)
        return f"Toolpaths generated successfully. Output saved to {gcode_path.name}.{sim_reason}"

    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-300:] if len(output) > 300 else output
        return f"G-Code generated successfully at {gcode_path}.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Slicing procedure failed: {err_msg}")
        return f"A critical failure occurred during G-Code generation:\n{err_msg}"


def transmit_gcode_http(
    target_url: str,
    gcode_path: Path,
    api_key: str = "",
    start_print: bool = False,
    dry_run: bool = False,
) -> str:
    """Transmits G-Code via HTTP multi-part upload to an OctoPrint/Moonraker API endpoint."""
    logger.info(f"Connecting to fabrication endpoint at {target_url}...")

    if dry_run:
        return (
            f"Transmission simulated (Dry Run). G-Code file {gcode_path.name} "
            f"prepared for delivery to {target_url} (start_print={start_print})."
        )

    try:
        upload_endpoint = f"{target_url.rstrip('/')}/api/files/local"
        boundary = "----CharonBoundary"

        content = gcode_path.read_bytes()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{gcode_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Content-Type": f"multipart/boundary={boundary}",
            "User-Agent": "Charon-Machinist/1.0",
        }
        if api_key:
            headers["X-Api-Key"] = api_key

        req = urllib.request.Request(
            upload_endpoint, data=body, headers=headers, method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.getcode()
            if status in (200, 201):
                return f"Transmission complete. Fabrication unit received {gcode_path.name} at {target_url}."
            else:
                return f"Printer responded with status code HTTP {status}."

    except (urllib.error.URLError, TimeoutError, Exception) as e:
        logger.warning(f"Hardware printer transmission failed or offline: {e}")
        return (
            f"Network transmission attempt to {target_url} ended. "
            f"G-Code file {gcode_path.name} is staged and ready for manual job dispatch ({e})."
        )

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/code.py`

```python
"""
charon/tools/code.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: tools/code.py
Module: Stateless utility functions for AST code auditing, workspace path extraction, and subshell sandbox execution.
"""

import ast
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from charon.config.paths import PROJECTS_DIR, resolve_project_path


def extract_target_directory(prompt: str) -> Optional[str]:
    """Dynamically resolves target workspace directories from explicit paths (POSIX & Windows),
    retrieved ledger rules, or relative project names within prompt text.
    """
    # Matches POSIX absolute paths (/foo/bar) and Windows paths (C:\foo\bar or C:/foo/bar)
    abs_matches = re.findall(
        r"(?:[a-zA-Z]:[\\/][\w.-]+(?:[\\/][\w.-]+)+|/(?:[\w.-]+(?:/[\w.-]+)+))",
        prompt,
    )
    abs_matches.sort(key=len, reverse=True)
    for match in abs_matches:
        path = Path(match)
        if path.is_dir():
            return str(path.resolve())
        elif path.parent.is_dir():
            return str(path.parent.resolve())

    base_dirs = []
    base_rule_matches = re.findall(
        r"(?:~/|/|[a-zA-Z]:[\\/])[a-zA-Z0-9_.-]+(?:[\\/][a-zA-Z0-9_.-]+)*",
        prompt,
    )
    for rule in base_rule_matches:
        expanded = Path(rule).expanduser()
        if expanded.is_dir():
            base_dirs.append(expanded)

    default_projects = PROJECTS_DIR
    if default_projects.is_dir() and default_projects not in base_dirs:
        base_dirs.append(default_projects)

    proj_match = re.search(
        r"(?:project|workspace|repo|bot)\s+([a-zA-Z0-9_.-]+)",
        prompt,
        re.IGNORECASE,
    )
    if proj_match:
        proj_name = proj_match.group(1).strip()
        try:
            resolved = resolve_project_path(proj_name)
            if resolved.is_dir():
                return str(resolved)
        except Exception:
            pass

        for base in base_dirs:
            candidate = base / proj_name
            if candidate.is_dir():
                return str(candidate.resolve())

    return None


def audit_written_artifacts(code: str, cwd: str) -> Tuple[bool, str]:
    """Parses code AST to detect file write calls via open() or Path.write_*()
    and verifies disk creation post-execution. Tracks simple variable assignments.
    """
    try:
        tree = ast.parse(code)
    except Exception as e:
        return False, f"AST Parse Error: {e}"

    created_files = []
    missing_files = []

    # Symbol tables for tracked variables
    str_vars: Dict[str, str] = {}
    path_vars: Dict[str, str] = {}

    for node in ast.walk(tree):
        # Track variable assignments: x = "file.txt" or p = Path("file.txt")
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id

                # Case 1: var = "filename.txt"
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    str_vars[var_name] = node.value.value

                # Case 2: var = Path("filename.txt") or Path(var2)
                elif (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "Path"
                    and node.value.args
                ):
                    arg0 = node.value.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(
                        arg0.value, str
                    ):
                        path_vars[var_name] = arg0.value
                    elif isinstance(arg0, ast.Name) and arg0.id in str_vars:
                        path_vars[var_name] = str_vars[arg0.id]

        if not isinstance(node, ast.Call):
            continue

        func = node.func
        target_filename: Optional[str] = None
        is_write_mode = False

        # --- open(...) Calls ---
        if isinstance(func, ast.Name) and func.id == "open":
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(
                    first_arg.value, str
                ):
                    target_filename = first_arg.value
                elif isinstance(first_arg, ast.Name) and first_arg.id in str_vars:
                    target_filename = str_vars[first_arg.id]

            mode = "r"
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            elif any(k.arg == "mode" for k in node.keywords):
                mode_kw = next(k for k in node.keywords if k.arg == "mode")
                if isinstance(mode_kw.value, ast.Constant):
                    mode = str(mode_kw.value.value)

            clean_mode = mode.translate(str.maketrans("", "", "rbt"))
            if clean_mode and any(m in clean_mode for m in ["w", "a", "x", "+"]):
                is_write_mode = True

        # --- Path methods (.write_text, .write_bytes, .open) ---
        elif isinstance(func, ast.Attribute) and func.attr in (
            "write_text",
            "write_bytes",
            "open",
        ):
            if func.attr in ("write_text", "write_bytes"):
                is_write_mode = True
            elif func.attr == "open":
                mode = "r"
                if node.args and isinstance(node.args[0], ast.Constant):
                    mode = str(node.args[0].value)
                elif any(k.arg == "mode" for k in node.keywords):
                    mode_kw = next(k for k in node.keywords if k.arg == "mode")
                    if isinstance(mode_kw.value, ast.Constant):
                        mode = str(mode_kw.value.value)

                clean_mode = mode.translate(str.maketrans("", "", "rbt"))
                if clean_mode and any(m in clean_mode for m in ["w", "a", "x", "+"]):
                    is_write_mode = True

            # Case A: Inline Path("out.txt").write_text(...)
            if (
                isinstance(func.value, ast.Call)
                and isinstance(func.value.func, ast.Name)
                and func.value.func.id == "Path"
            ):
                if (
                    func.value.args
                    and isinstance(func.value.args[0], ast.Constant)
                    and isinstance(func.value.args[0].value, str)
                ):
                    target_filename = func.value.args[0].value
                elif (
                    func.value.args
                    and isinstance(func.value.args[0], ast.Name)
                    and func.value.args[0].id in str_vars
                ):
                    target_filename = str_vars[func.value.args[0].id]

            # Case B: Variable path p.write_text(...) where p was assigned Path(...)
            elif isinstance(func.value, ast.Name) and func.value.id in path_vars:
                target_filename = path_vars[func.value.id]

        if is_write_mode and target_filename:
            target_path = Path(cwd) / target_filename
            if target_path.exists():
                created_files.append(str(target_path))
            else:
                missing_files.append(str(target_path))

    if missing_files:
        prefix = (
            f"{len(created_files)} file artifact(s) created. "
            if created_files
            else ""
        )
        return (
            False,
            f"{prefix}AST Disk Audit Warning: Script reported success, but expected output file(s) were missing on disk: {', '.join(missing_files)}",
        )

    audit_msg = (
        f"AST Disk Audit Verified: {len(created_files)} file artifact(s) created."
        if created_files
        else "AST Disk Audit Passed (No disk write calls detected)."
    )
    return True, audit_msg


async def run_script_in_subprocess(
    code: str,
    cwd: str,
    python_cmd: str = sys.executable,
    timeout: float = 30.0,
    stream_callback: Optional[Callable[[str], None]] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[str, bool]:
    """Executes a code string in an isolated temporary Python subshell with strict execution timeout limits."""
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    )
    try:
        temp_file.write(code)
        temp_file.flush()
        temp_file.close()

        exec_kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if os.path.exists(cwd):
            exec_kwargs["cwd"] = cwd

        if env is not None:
            exec_kwargs["env"] = env

        process = await asyncio.create_subprocess_exec(
            python_cmd, temp_file.name, **exec_kwargs
        )

        output_chunks: list[str] = []

        async def _read_stream(stream: Optional[asyncio.StreamReader]):
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                chunk = line.decode("utf-8", errors="replace")
                output_chunks.append(chunk)
                if stream_callback:
                    try:
                        stream_callback(chunk)
                    except Exception:
                        pass

        async def _run_and_read() -> int:
            stream_tasks = []
            if process.stdout is not None:
                stream_tasks.append(_read_stream(process.stdout))
            if process.stderr is not None and process.stderr != process.stdout:
                stream_tasks.append(_read_stream(process.stderr))

            if stream_tasks:
                await asyncio.gather(*stream_tasks)

            await process.wait()
            return process.returncode if process.returncode is not None else -1

        try:
            task = asyncio.create_task(_run_and_read())
            return_code = await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return (
                f"Execution TimeoutError: Process terminated after exceeding {timeout}s limit.",
                False,
            )

        full_output = "".join(output_chunks).strip()
        return full_output, (return_code == 0)

    except Exception as e:
        return f"Execution Error: {str(e)}", False
    finally:
        if os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/eda.py`

```python
"""
charon/tools/eda.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tool wrappers for KiCad CLI Gerber and BOM generation.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Charon.Tools.EDA")


def export_kicad_gerbers(
    pcb_path: Path,
    kicad_cli: str = "kicad-cli",
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Automates KiCad CLI to plot production PCB Gerber and drill files."""
    if output_dir is None:
        output_dir = pcb_path.parent / "gerbers"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        kicad_cli,
        "pcb",
        "export",
        "gerbers",
        "-o",
        str(output_dir),
        str(pcb_path),
    ]

    logger.info(f"Exporting Gerbers for {pcb_path.name} to {output_dir}")

    if dry_run or not shutil.which(kicad_cli):
        sim_note = (
            " (Simulated: KiCad CLI not found)"
            if not shutil.which(kicad_cli)
            else " (Dry Run)"
        )
        return f"Gerber fabrication files successfully plotted to {output_dir}.{sim_note}"

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        drill_cmd = [
            kicad_cli,
            "pcb",
            "export",
            "drl",
            "-o",
            str(output_dir),
            str(pcb_path),
        ]
        subprocess.run(drill_cmd, check=True, capture_output=True, text=True)

        return f"Gerber fabrication & drill files successfully generated in {output_dir}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Gerber export failed: {err_msg}")
        return f"A failure occurred during KiCad EDA Gerber export:\n{err_msg}"


def export_kicad_bom(
    pcb_path: Path,
    kicad_cli: str = "kicad-cli",
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Automates KiCad CLI to export Bill of Materials (BOM) CSV."""
    if output_dir is None:
        output_dir = (
            pcb_path.parent / "bom"
            if (pcb_path.parent / "bom").parent.exists()
            else pcb_path.parent
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / f"{pcb_path.stem}_bom.csv"

    sch_path = pcb_path.with_suffix(".kicad_sch")
    cmd = [
        kicad_cli,
        "sch",
        "export",
        "bom",
        "-o",
        str(output_csv),
        str(sch_path),
    ]

    logger.info(f"Exporting BOM for {pcb_path.name} to {output_csv}")

    if dry_run or not shutil.which(kicad_cli):
        sim_note = (
            " (Simulated: KiCad CLI not found)"
            if not shutil.which(kicad_cli)
            else " (Dry Run)"
        )
        return f"Bill of Materials (BOM) exported successfully to {output_csv}.{sim_note}"

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Bill of Materials (BOM) exported successfully to {output_csv}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"BOM export failed: {err_msg}")
        return f"A failure occurred during KiCad BOM export:\n{err_msg}"

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/firmware.py`

```python
"""
charon/tools/firmware.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tool wrappers for PlatformIO firmware operations.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("Charon.Tools.Firmware")


def compile_platformio_firmware(
    target_path: Path,
    pio_cmd: str = "pio",
    environment: str = "",
    dry_run: bool = False,
) -> str:
    """Triggers a PlatformIO build sequence for embedded firmware."""
    ini_file = target_path / "platformio.ini"
    if not ini_file.exists():
        return f"Error: No PlatformIO configuration (platformio.ini) found in {target_path}."

    cmd = [pio_cmd, "run"]
    if environment:
        cmd.extend(["-e", str(environment)])

    logger.info(
        f"Initiating firmware compilation in {target_path} using command: {' '.join(cmd)}"
    )

    if dry_run or not shutil.which(pio_cmd):
        sim_note = (
            " (Simulated: PlatformIO CLI not found)"
            if not shutil.which(pio_cmd)
            else " (Dry Run)"
        )
        return (
            f"Firmware compilation simulated successfully for environment "
            f"'{environment or 'default'}' in {target_path}.{sim_note}"
        )

    try:
        result = subprocess.run(
            cmd, cwd=target_path, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-500:] if len(output) > 500 else output
        return f"Firmware compiled successfully for environment '{environment or 'default'}'.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Compilation failed in {target_path}: {err_msg}")
        return f"Firmware compilation failed:\n{err_msg}"


def flash_platformio_firmware(
    target_path: Path,
    pio_cmd: str = "pio",
    port: str = "auto",
    environment: str = "",
    dry_run: bool = False,
) -> str:
    """Pushes compiled binaries via serial/USB to target microcontroller."""
    cmd = [pio_cmd, "run", "--target", "upload"]
    if environment:
        cmd.extend(["-e", str(environment)])
    if port and port != "auto":
        cmd.extend(["--upload-port", str(port)])

    logger.info(f"Attempting to flash hardware on port '{port}' from {target_path}...")

    if dry_run or not shutil.which(pio_cmd):
        sim_note = (
            " (Simulated: PlatformIO CLI not found)"
            if not shutil.which(pio_cmd)
            else " (Dry Run)"
        )
        return (
            f"Firmware upload sequence simulated successfully on port '{port}' "
            f"in {target_path}.{sim_note}"
        )

    try:
        result = subprocess.run(
            cmd, cwd=target_path, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-500:] if len(output) > 500 else output
        return f"Firmware successfully flashed to target hardware on port '{port}'.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Hardware flash failed: {err_msg}")
        return f"Failed to write to target microcontroller on port '{port}':\n{err_msg}"

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/git.py`

```python
"""
charon/tools/git.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: tools/git.py
Module: Stateless Git operations for Charon tools and agents.
"""

import logging
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("CHAROND.Tools.Git")


def git_init(target_path: Path) -> Tuple[bool, str]:
    """Initializes a new Git repository at the target path.

    Returns:
        Tuple[bool, str]: (success, status_or_error_message)
    """
    try:
        subprocess.run(
            ["git", "init"],
            cwd=target_path,
            check=True,
            capture_output=True,
        )
        logger.info(f"Git initialized in {target_path}")
        return True, "Initialized successfully"
    except subprocess.CalledProcessError as e:
        err_output = (
            e.stderr.decode().strip()
            if e.stderr
            else str(e)
        )
        logger.error(f"Git initialization failed: {err_output}")
        return False, f"Failed ({err_output})"
    except FileNotFoundError:
        logger.error("Git executable not found on system.")
        return False, "Git executable not found on system"


def git_commit(target_path: Path, commit_message: str) -> Tuple[bool, str, str]:
    """Stages all changes and commits them in the target Git repository.

    Returns:
        Tuple[bool, str, str]: (success, status_code, message_or_error)
        status_code options: "clean", "committed", "failed", "no_git", "no_exe"
    """
    if not (target_path / ".git").exists():
        return (
            False,
            "no_git",
            f"Execution aborted: Target directory {target_path} is not under Git version control.",
        )

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=target_path,
            check=True,
            capture_output=True,
        )

        if not status.stdout.strip():
            logger.info(f"Workspace {target_path} is clean. No commit necessary.")
            return True, "clean", "Skipped (Workspace is already clean)"

        subprocess.run(
            ["git", "add", "."],
            cwd=target_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=target_path,
            check=True,
            capture_output=True,
        )

        logger.info(f"Workspace committed: {commit_message}")
        return True, "committed", commit_message

    except subprocess.CalledProcessError as e:
        err = (
            (e.stderr.decode().strip() if e.stderr else "")
            or (e.stdout.decode().strip() if e.stdout else "")
            or str(e)
        )
        logger.error(f"Git commit failed in {target_path}: {err}")
        return False, "failed", err
    except FileNotFoundError:
        return False, "no_exe", "Warning: Git executable not found on system."

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/iot.py`

```python
"""
charon/tools/iot.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tools for Home Assistant REST and MQTT messaging.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Union

try:
    import paho.mqtt.publish as mqtt_publish

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

logger = logging.getLogger("Charon.Tools.IoT")


def make_ha_request(
    ha_url: str,
    ha_token: str,
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Executes HTTP REST requests against a Home Assistant instance."""
    if not ha_token:
        return {
            "status": "error",
            "message": "HOMEASSISTANT_TOKEN environment variable is not configured.",
        }

    url = f"{ha_url.rstrip('/')}{endpoint}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }

    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data_bytes, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            return {
                "status": "success",
                "code": response.status,
                "data": json.loads(res_body) if res_body else {},
            }
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8") if e.fp else str(e)
        logger.error(f"[IOT TOOL] Home Assistant REST error [{e.code}]: {err_text}")
        return {"status": "error", "code": e.code, "message": err_text}
    except Exception as e:
        logger.error(f"[IOT TOOL] Failed to connect to Home Assistant at {url}: {e}")
        return {"status": "error", "message": str(e)}


def publish_mqtt_message(
    topic: str,
    payload: Optional[Union[Dict[str, Any], str]] = None,
    host: str = "localhost",
    port: int = 1883,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Publishes a raw payload to an MQTT topic."""
    if not MQTT_AVAILABLE:
        return {
            "status": "error",
            "message": "paho-mqtt library is not installed in the environment.",
        }

    if not topic:
        return {
            "status": "error",
            "message": "MQTT topic is required for publish_mqtt.",
        }

    msg_payload = (
        json.dumps(payload) if isinstance(payload, dict) else str(payload or "")
    )

    auth = None
    if user and password:
        auth = {"username": user, "password": password}

    try:
        logger.info(f"[IOT TOOL] Publishing MQTT message to topic: {topic}")
        mqtt_publish.single(
            topic=topic,
            payload=msg_payload,
            hostname=host,
            port=port,
            auth=auth,
        )
        return {
            "action": "publish_mqtt",
            "topic": topic,
            "payload": payload,
            "status": "success",
        }
    except Exception as e:
        logger.error(f"[IOT TOOL] MQTT publish failed: {e}")
        return {"status": "error", "topic": topic, "message": str(e)}

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/math.py`

```python
"""
charon/tools/math.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Safe AST Mathematical Evaluation Tools.
"""

import ast
import math
from typing import Optional, Union


def safe_eval_math(expr: str) -> Optional[Union[int, float]]:
    """Safely evaluates pure arithmetic expressions using Python AST parsing."""
    try:
        clean_expr = expr.replace("^", "**").strip()
        node = ast.parse(clean_expr, mode="eval")

        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.USub,
            ast.UAdd,
        )

        for subnode in ast.walk(node):
            if not isinstance(subnode, allowed_nodes):
                return None
            # Explicitly reject boolean constants during AST traversal
            if isinstance(subnode, ast.Constant) and isinstance(subnode.value, bool):
                return None

        code = compile(node, "<string>", "eval")
        result = eval(code, {"__builtins__": None, "math": math}, {})

        # Python evaluates isinstance(True, int) as True.
        # We must explicitly exclude bools before checking for int/float.
        if isinstance(result, bool):
            return None

        if isinstance(result, (int, float)):
            return result
    except Exception:
        return None
    return None

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/pdf.py`

```python
"""
charon/tools/pdf.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Reusable tool utilities for PDF parsing, retrieval, and text processing.
"""

import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

logger = logging.getLogger("CHAROND.Tools.PDF")


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    text_len = len(cleaned)
    step = max(1, chunk_size - overlap)

    while start < text_len:
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        start += step

    return chunks


def sanitize_metadata(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    if not metadata:
        return {}

    clean_meta = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean_meta[k] = v
        else:
            clean_meta[k] = str(v)
    return clean_meta


def extract_text_from_pdf(pdf_path: Path) -> List[Tuple[int, str]]:
    if not PYPDF_AVAILABLE:
        raise ImportError("The 'pypdf' package is required for PDF operations. Run 'pip install pypdf'.")

    resolved = pdf_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Cannot process non-existent PDF file: {resolved}")

    reader = PdfReader(resolved)
    page_texts = []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text()
            if text and text.strip():
                page_texts.append((page_num, text))
        except Exception as err:
            logger.warning(f"Failed to extract text from page {page_num} of {resolved.name}: {err}")

    return page_texts


def download_pdf_bytes(url: str, timeout: int = 25) -> bytes:
    """Downloads PDF binary payload with standard headers, 25s timeout, and curl fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",  # Removed 'br' to prevent unhandled Brotli streams in urllib
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
            if b"%PDF" in content[:1024]:
                return content
    except Exception as e:
        logger.warning(f"Standard urllib fetch failed for {url} ({e}); attempting curl fallback...")

    try:
        cmd = [
            "curl",
            "-sSL",
            "--compressed",
            "-A", headers["User-Agent"],
            "-H", f"Accept: {headers['Accept']}",
            "-H", f"Accept-Language: {headers['Accept-Language']}",
            "--max-time", str(timeout),
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, check=True)
        if b"%PDF" in res.stdout[:1024]:
            return res.stdout
    except Exception as e:
        logger.error(f"curl fallback failed for {url}: {e}")

    raise ValueError(f"Unable to retrieve valid PDF payload from {url}.")

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/system.py`

```python
"""
charon/tools/system.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless System Diagnostics, Telemetry & Shell Execution Tools.
"""

import asyncio
import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from charon.config.paths import DATA_DIR

logger = logging.getLogger("Charon.Tools.System")


def get_system_info() -> str:
    """Gathers hardware, operating system, and runtime diagnostic info."""
    info = [
        f"OS: {platform.system()} {platform.release()} ({platform.architecture()[0]})",
        f"Python Version: {sys.version.split()[0]} ({sys.executable})",
        f"Hostname: {platform.node()}",
        f"Processor: {platform.processor() or 'Generic/System Native'}",
        f"Working Directory: {Path.cwd()}",
    ]

    if PSUTIL_AVAILABLE:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        info.append(f"CPU Load: {cpu_usage}%")
        info.append(
            f"RAM Usage: {mem.percent}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)"
        )
        info.append(
            f"Disk Usage: {disk.percent}% ({disk.free // (1024**3)}GB free)"
        )
    else:
        info.append(
            "psutil: Not installed (detailed hardware usage unavailable)"
        )

    return "System Status & Metrics:\n" + "\n".join(
        f"- {line}" for line in info
    )


def get_system_telemetry() -> Dict[str, Any]:
    """Retrieves structured OS host telemetry including CPU, RAM, RSS, and disk usage."""
    telemetry: Dict[str, Any] = {}

    if PSUTIL_AVAILABLE:
        vm = psutil.virtual_memory()
        proc = psutil.Process()
        telemetry["telemetry"] = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": vm.percent,
            "ram_available_mb": round(vm.available / (1024 * 1024), 2),
            "daemon_ram_rss_mb": round(
                proc.memory_info().rss / (1024 * 1024), 2
            ),
            "daemon_cpu_percent": proc.cpu_percent(interval=None),
        }
    else:
        telemetry["telemetry"] = {"psutil": "not_installed"}

    try:
        total, used, free = shutil.disk_usage(str(DATA_DIR.parent))
        telemetry["disk_usage"] = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "percent_used": round((used / total) * 100, 2),
        }
    except Exception as e:
        telemetry["disk_usage_error"] = str(e)

    return telemetry


async def execute_shell_command(
    command_str: str,
    timeout: float = 30.0,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """Executes a shell command asynchronously with streaming output and timeout enforcement."""
    logger.info(f"Executing OS command: {command_str}")

    try:
        process = await asyncio.create_subprocess_shell(
            command_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_chunks = []

        async def _read_stream():
            if process.stdout is None:
                return
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                chunk = line.decode("utf-8", errors="replace")
                output_chunks.append(chunk)
                if stream_callback:
                    stream_callback(chunk)

        try:
            await asyncio.wait_for(_read_stream(), timeout=timeout)
            await process.wait()
            return_code = process.returncode
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"Command Execution Status: Failed (Execution timed out after {timeout}s)\n\nOutput:\nProcess killed due to timeout."

        full_output = "".join(output_chunks).strip()

        status = (
            "Success"
            if return_code == 0
            else f"Failed (exit code {return_code})"
        )
        output_display = (
            full_output
            if full_output
            else "(Command executed with no terminal output)"
        )
        return f"Command Execution Status: {status}\n\nOutput:\n{output_display}"

    except Exception as e:
        logger.error(f"Failed to execute system command '{command_str}': {e}")
        return f"System task execution error: {str(e)}"

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/tools/web.py`

```python
"""
charon/tools/web.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Pure, domain-agnostic web search and HTTP scraping tools.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

# Defensive package detection for DuckDuckGo search
try:
    from ddgs import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS

        DDGS_AVAILABLE = True
    except ImportError:
        DDGS = None
        DDGS_AVAILABLE = False

# Defensive package detection for Google search
try:
    from googlesearch import search as google_search

    GOOGLE_AVAILABLE = True
except ImportError:
    google_search = None
    GOOGLE_AVAILABLE = False

logger = logging.getLogger("Charon.Tools.Web")


def clean_search_query(query: str) -> str:
    """Strips common LLM quote prefixes, Markdown tags, or formatting artifacts."""
    cleaned = str(query).strip()
    return re.sub(r"^[`'\">]+|[`'\">]+$", "", cleaned).strip()


def execute_web_search(
    query: str,
    max_results: int = 5,
    ignored_domains: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Performs web search via DuckDuckGo with fallback to Google.

    Returns raw dictionaries: [{'title': str, 'link': str, 'snippet': str}].
    """
    cleaned_query = clean_search_query(query)
    if not cleaned_query:
        return []

    try:
        safe_max = max(1, int(max_results))
    except (ValueError, TypeError):
        safe_max = 5

    ignored = [d.lower() for d in (ignored_domains or [])]
    results: List[Dict[str, str]] = []

    # Primary Search Engine: DuckDuckGo / DDGS
    if DDGS_AVAILABLE and DDGS is not None:
        try:
            with DDGS() as ddgs:
                ddg_hits = list(ddgs.text(cleaned_query, max_results=safe_max * 2))
                for item in ddg_hits:
                    link = str(item.get("href") or item.get("link", "#"))
                    if any(domain in link.lower() for domain in ignored):
                        continue

                    results.append(
                        {
                            "title": str(item.get("title", "Untitled")).strip(),
                            "link": link,
                            "snippet": str(item.get("body", "")).strip(),
                        }
                    )
                    if len(results) >= safe_max:
                        break
        except Exception as e:
            logger.warning(
                f"DDGS search failed for '{cleaned_query}': {e}. Falling back to Google..."
            )

    # Secondary Fallback: Google Search
    if not results and GOOGLE_AVAILABLE and google_search is not None:
        try:
            g_hits = list(
                google_search(
                    cleaned_query,
                    num_results=safe_max * 2,
                    advanced=True,
                )
            )
            for item in g_hits:
                if isinstance(item, str):
                    link = item
                    title = "Google Result"
                    snippet = ""
                else:
                    link = str(getattr(item, "url", getattr(item, "link", "#")))
                    raw_title = getattr(item, "title", None)
                    title = raw_title if isinstance(raw_title, str) else "Google Result"
                    raw_snippet = getattr(item, "description", getattr(item, "snippet", None))
                    snippet = raw_snippet if isinstance(raw_snippet, str) else ""

                if any(domain in link.lower() for domain in ignored):
                    continue

                results.append(
                    {
                        "title": str(title).strip(),
                        "link": link,
                        "snippet": str(snippet).strip(),
                    }
                )
                if len(results) >= safe_max:
                    break
        except Exception as e:
            logger.error(f"Google search fallback failed: {e}")

    return results


def fetch_url_raw_content(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_chars: int = 4000,
) -> Dict[str, Any]:
    """Fetches a URL via HTTP, extracts clean text from HTML/JSON/Text, and returns a result dict."""
    target_url = str(url).strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    default_headers = headers or {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        with httpx.Client(
            timeout=12.0, follow_redirects=True, headers=default_headers
        ) as client:
            res = client.get(target_url)
            res.raise_for_status()

        content_type = res.headers.get("content-type", "").lower()

        if "text/plain" in content_type or "application/json" in content_type:
            clean_text = re.sub(r"\s+", " ", res.text).strip()
            page_title = "Raw Content"
        else:
            soup = BeautifulSoup(res.text, "html.parser")
            page_title = (
                soup.title.string.strip()
                if soup.title and soup.title.string
                else "No Title"
            )

            for element in soup(
                [
                    "head",
                    "title",
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "noscript",
                    "svg",
                    "iframe",
                    "form",
                    "aside",
                    "button",
                ]
            ):
                element.decompose()

            raw_text = soup.get_text(separator=" ", strip=True)
            clean_text = re.sub(r"\s+", " ", raw_text).strip()

        if not clean_text:
            return {
                "success": True,
                "url": target_url,
                "title": page_title,
                "content": "",
                "message": f"Page at '{target_url}' was fetched successfully but contained no extractable text.",
            }

        truncated = False
        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars]
            truncated = True

        return {
            "success": True,
            "url": target_url,
            "title": page_title,
            "content": clean_text,
            "truncated": truncated,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP status error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": f"HTTP Status {e.response.status_code}",
        }
    except httpx.RequestError as e:
        logger.error(f"Network error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": "Network connection error.",
        }
    except Exception as e:
        logger.error(f"Scrape error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": str(e),
        }

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/utils/__init__.py`

```python
"""
charon/utils/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package initialization gateway for utils.
"""


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/utils/memory.py`

```python
"""
charon/utils/memory.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Charon Memory Utilities: Rolling Conversation Buffer for Prompt Context.
"""

import logging
from typing import Dict, List

logger = logging.getLogger("Charon.Utils.Memory")


class ConversationBuffer:
    """Rolling RAM memory buffer to maintain short-term context across D-Bus transmissions."""

    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []

    def add_user_message(self, text: str) -> None:
        """Appends a user prompt to context."""
        self.add_turn("user", text)

    def add_system_message(self, text: str) -> None:
        """Appends a Charon daemon response to context."""
        self.add_turn("assistant", text)

    def add_turn(self, role: str, content: str) -> None:
        """Appends a single turn and enforces max context length."""
        self.history.append({"role": role, "content": content})
        # Keep only the last (max_turns * 2) individual messages
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2) :]

    def get_context_string(self) -> str:
        """Formats buffered history into a plain text block for model system prompts."""
        if not self.history:
            return "No prior conversational context."

        formatted = []
        for msg in self.history:
            speaker = "User" if msg["role"].lower() in ["user", "human"] else "Charon"
            formatted.append(f"{speaker}: {msg['content']}")
        return "\n".join(formatted)

    def clear(self) -> None:
        """Flushes active context buffer (e.g., on topic change or exit)."""
        self.history.clear()
        logger.info("Conversation memory buffer cleared.")

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/audit_agent_skill_map.py`

```python
#!/usr/bin/env python3
"""
scripts/audit_agent_skill_map.py
System Version: v0.6.7

Audits agent skill mappings by comparing physical manifest metadata against
agent_registry, skill_registry, and agent_skill_map in SQLite.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def audit_agent_skill_mappings():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # 1. Fetch registered agents
    cursor.execute("SELECT agent_id, display_name, is_active FROM agent_registry;")
    agents = {row[0]: {"display_name": row[1], "is_active": row[2]} for row in cursor.fetchall()}

    # 2. Fetch registered skills
    cursor.execute("SELECT skill_id, action_name, status FROM skill_registry;")
    db_skills = {row[0]: {"action_name": row[1], "status": row[2]} for row in cursor.fetchall()}

    # 3. Fetch agent_skill_map
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    db_map = cursor.fetchall()

    # 4. Read Manifest files for disk-side agent references
    manifest_agent_refs = {}
    if SKILLS_DIR.exists():
        for m_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                s_id = data.get("skill_id", m_path.parent.name)
                declared_agent = (
                        data.get("agent_id")
                        or data.get("assigned_agent")
                        or data.get("target_agent")
                        or data.get("agent")
                        or data.get("role")
                )
                manifest_agent_refs[s_id] = declared_agent
            except Exception:
                pass

    print("\n" + "=" * 70)
    print(" 🤖 CHARON AGENT <-> SKILL MAP AUDIT")
    print("=" * 70)

    # Agent Summary
    print(f"\n📋 REGISTERED AGENTS IN `agent_registry` ({len(agents)} Total):")
    for a_id, info in agents.items():
        status_str = "ACTIVE" if info["is_active"] else "INACTIVE"
        print(f"  • [{a_id}] ({info['display_name']}) -> {status_str}")

    # Outdated Agents Check
    invalid_agents_in_map = [row for row in db_map if row[0] not in agents]
    invalid_skills_in_map = [row for row in db_map if row[1] not in db_skills]

    print(f"\n🔗 DB `agent_skill_map` RECORDS ({len(db_map)} Total Mappings):")
    if invalid_agents_in_map:
        print(f"\n⚠️ OUTDATED / UNREGISTERED AGENT IDs IN `agent_skill_map` ({len(invalid_agents_in_map)}):")
        for a_id, s_id in invalid_agents_in_map:
            print(f"  ❌ Agent ID '{a_id}' mapped to Skill '{s_id}' (Agent missing from agent_registry)")
    else:
        print("  ✅ All mapped `agent_id` records match valid agents in `agent_registry`.")

    if invalid_skills_in_map:
        print(f"\n⚠️ UNINDEXED / MISSING SKILL IDs IN `agent_skill_map` ({len(invalid_skills_in_map)}):")
        for a_id, s_id in invalid_skills_in_map:
            print(f"  ❌ Skill ID '{s_id}' mapped to Agent '{a_id}' (Skill missing from skill_registry)")
    else:
        print("  ✅ All mapped `skill_id` records match valid skills in `skill_registry`.")

    # Manifest vs DB Mapping Discrepancies
    discrepancies = []
    for s_id, decl_agent in manifest_agent_refs.items():
        if decl_agent:
            mapped_agents = [a_id for a_id, skill in db_map if skill == s_id]
            if decl_agent not in mapped_agents:
                discrepancies.append((s_id, decl_agent, mapped_agents))

    if discrepancies:
        print(f"\n⚠️ MANIFEST DECLARATION VS DB MAPPING DISCREPANCIES ({len(discrepancies)}):")
        for s_id, decl_agent, mapped_agents in discrepancies:
            print(f"  - Skill: '{s_id}'")
            print(f"    • Manifest Specifies : '{decl_agent}'")
            print(f"    • DB Map Contains    : {mapped_agents if mapped_agents else 'NONE'}")
    else:
        print("  ✅ No manifest-to-database agent assignment conflicts detected.")

    print("\n" + "=" * 70 + "\n")
    conn.close()


if __name__ == "__main__":
    audit_agent_skill_mappings()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/audit_and_purge_skills.py`

```python
#!/usr/bin/env python3
"""
scripts/audit_and_purge_skills.py
System Version: v0.6.1

Audit and database purging tool to inspect skill_registry for AI-hallucinated skills
and clean up orphan/ghost entries across skill_registry, agent_skill_map,
skill_gaps, and skill_permissions safely with dynamic schema introspection.
"""

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Set

# Standard Charon Config Path Fallback
try:
    from charon.config.paths import STATE_DB_PATH
except ImportError:
    STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.Maintenance.PurgeSkills")

# Ground Truth List of 38 Verified On-Disk Skill Directory Names
GROUND_TRUTH_SKILLS: Set[str] = {
    "archivist_datasheet_rag",
    "archivist_vector_ledger",
    "cleaner_cad_sweeper",
    "cleaner_git_manager",
    "cleaner_log_pruner",
    "cleaner_workspace_deleter",
    "cleaner_workspace_inspector",
    "cleaner_workspace_scaffolder",
    "code_python_interpreter",
    "code_sandbox_executor",
    "code_script_generator",
    "code_self_healing_solver",
    "extract_pdf_ocr_skill",
    "fab_cad_tools",
    "fab_cam_slicer",
    "fab_printer_transmitter",
    "generalist_math_evaluator",
    "generalist_query_handler",
    "generalist_rag_synthesizer",
    "generalist_system_executor",
    "generalist_system_inspector",
    "hw_eda_kicad",
    "hw_firmware_pio",
    "iot_home_assistant",
    "iot_mqtt_publisher",
    "kicad_bom_exporter",
    "plan_task_decomposer",
    "quartermaster_bom_auditor",
    "quartermaster_datasheet_fetcher",
    "quartermaster_inventory_manager",
    "skill_builder",
    "sys_asset_pruner",
    "sys_health_auditor",
    "sys_log_analyzer",
    "sys_os_control",
    "task_tracker_manage",
    "web_scraper",
    "web_search",
}


def get_table_columns(cursor: sqlite3.Cursor, table_name: str) -> Set[str]:
    """Helper to dynamically fetch column names for a table."""
    try:
        cursor.execute(f"PRAGMA table_info({table_name});")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()


def audit_and_purge_db(db_path: Path, dry_run: bool = False) -> None:
    """Audits skill_registry against ground-truth and purges invalid/hallucinated rows across all linked tables."""
    if not db_path.exists():
        logger.error(f"Database file not found at: {db_path}")
        sys.exit(1)

    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # 1. Fetch current database state
        cursor.execute("SELECT * FROM skill_registry;")
        rows = cursor.fetchall()

        valid_skills: List[Dict] = []
        hallucinated_skills: List[Dict] = []

        for row in rows:
            r_dict = dict(row)
            skill_id = r_dict.get("skill_id", "")
            action_name = r_dict.get("action_name", "")

            # Check if skill matches ground truth either by ID or action name
            if skill_id in GROUND_TRUTH_SKILLS or action_name in GROUND_TRUTH_SKILLS:
                valid_skills.append(r_dict)
            else:
                hallucinated_skills.append(r_dict)

        # 2. Display Audit Summary
        print("\n" + "=" * 80)
        print(" 📊 SKILL REGISTRY AUDIT REPORT")
        print("=" * 80)
        print(f" Total Registered Skills in DB : {len(rows)}")
        print(f" Verified / Valid Skills On-Disk: {len(valid_skills)}")
        print(f" Hallucinated / Ghost Skills    : {len(hallucinated_skills)}")
        print("=" * 80 + "\n")

        if not hallucinated_skills:
            logger.info("✨ Database is clean! No hallucinated skills detected.")
            return

        print("🚨 HALLUCINATED / GHOST SKILLS TO BE PURGED:")
        print("-" * 80)
        print(f"{'SKILL ID':<35} | {'ACTION NAME':<30} | {'STATUS':<10}")
        print("-" * 80)

        junk_ids: Set[str] = set()
        junk_actions: Set[str] = set()

        for junk in hallucinated_skills:
            s_id = junk.get("skill_id", "")
            a_name = junk.get("action_name", "")
            status = junk.get("status", "")

            if s_id:
                junk_ids.add(s_id)
            if a_name:
                junk_actions.add(a_name)

            print(f"{s_id:<35} | {a_name:<30} | {status:<10}")

        print("-" * 80 + "\n")

        if dry_run:
            logger.info("🔍 Dry-run mode enabled. No changes were committed.")
            return

        # 3. Perform Dynamic Atomic Purge
        logger.info("Starting multi-table atomic purge with dynamic schema matching...")
        conn.execute("BEGIN TRANSACTION;")

        deleted_counts: Dict[str, int] = {}
        all_junk_terms = list(junk_ids.union(junk_actions))

        # Helper function for safe conditional table deletion
        def safe_delete_from_table(table_name: str, target_fields: List[str]) -> int:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
            if not cursor.fetchone():
                return 0

            existing_cols = get_table_columns(cursor, table_name)
            matched_cols = [col for col in target_fields if col in existing_cols]

            if not matched_cols:
                return 0

            ph = ",".join("?" * len(all_junk_terms))
            where_conditions = [f"{col} IN ({ph})" for col in matched_cols]
            sql = f"DELETE FROM {table_name} WHERE {' OR '.join(where_conditions)};"

            # Multiply parameter tuple for each matched column condition
            params = all_junk_terms * len(matched_cols)
            cursor.execute(sql, params)
            return cursor.rowcount

        # Execute safe dynamic purge across linked tables
        deleted_counts["skill_permissions"] = safe_delete_from_table("skill_permissions", ["skill_id", "perm_id"])
        deleted_counts["agent_skill_map"] = safe_delete_from_table("agent_skill_map", ["skill_id", "agent_id"])
        deleted_counts["skill_gaps"] = safe_delete_from_table("skill_gaps",
                                                              ["skill_id", "action_name", "required_skill",
                                                               "missing_skill"])
        deleted_counts["skill_registry"] = safe_delete_from_table("skill_registry", ["skill_id", "action_name"])

        conn.commit()

        print("=" * 80)
        print(" 🧹 CLEANUP COMPLETE")
        print("=" * 80)
        for tbl, count in deleted_counts.items():
            print(f" Removed from '{tbl}': {count} records")
        print("=" * 80 + "\n")
        logger.info("Database state successfully synchronized with physical filesystem.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to purge database! Transaction rolled back. Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit and purge hallucinated skills from state.db")
    parser.add_argument("--db", type=str, default=str(STATE_DB_PATH), help="Path to state.db")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without deleting")
    args = parser.parse_args()

    audit_and_purge_db(Path(args.db), dry_run=args.dry_run)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/bootstrap_agents.py`

```python
import os
import json
import sqlite3
from pathlib import Path

# Paths based on your Charon environment
DB_PATH = os.path.expanduser("~/.local/share/charon/charon_state.db")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "charon", "agents")


def bootstrap_database():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("=== Initiating Clean Slate Protocol ===")
        # Disable foreign keys temporarily to allow unrestricted wiping of junk data
        cursor.execute("PRAGMA foreign_keys = OFF;")

        tables_to_purge = [
            "agent_skill_map",
            "skill_registry",
            "route_registry",
            "system_roles",
            "skill_gaps",
            "agent_registry"
        ]

        for table in tables_to_purge:
            cursor.execute(f"DELETE FROM {table};")
            print(f"Purged table: {table}")

        # Re-enable foreign keys for safe insertion
        cursor.execute("PRAGMA foreign_keys = ON;")

        print("\n=== Rebuilding Source of Truth ===")
        agent_specs = list(Path(AGENTS_DIR).rglob("staging/agent_spec.json"))

        if not agent_specs:
            print(f"No agent_spec.json files found in {AGENTS_DIR}/*/staging/")
            return

        for spec_path in agent_specs:
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)

            agent_id = spec.get("agent_id")
            display_name = spec.get("display_name")
            description = spec.get("description", "")
            default_action = spec.get("default_action", "idle")
            system_prompt = spec.get("system_prompt", "")
            role_name = spec.get("role_name")

            if not agent_id:
                print(f"Skipping {spec_path}: Missing 'agent_id'")
                continue

            print(f"Registering Agent: {display_name} ({agent_id})")

            # 1. Insert into agent_registry
            cursor.execute("""
                INSERT INTO agent_registry 
                (agent_id, display_name, description, default_action, system_prompt)
                VALUES (?, ?, ?, ?, ?)
            """, (agent_id, display_name, description, default_action, system_prompt))

            # 2. Insert into system_roles (if a role is defined)
            if role_name:
                print(f"  -> Assigning Role: {role_name}")
                cursor.execute("""
                    INSERT INTO system_roles (role_name, agent_id, description)
                    VALUES (?, ?, ?)
                """, (role_name, agent_id, f"Primary role for {display_name}"))

        conn.commit()
        print("\n=== Bootstrapping Complete ===")
        print("The database is clean. You are cleared to run 'reindex_skills'.")

    except Exception as e:
        conn.rollback()
        print(f"\nFailed during bootstrapping: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    bootstrap_database()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/bootstrap_skill_builder.py`

```python
"""
scripts/bootstrap_skill_builder.py
Programmatically constructs and promotes the meta skill 'skill_builder' into dynamic production.
"""

import json
import logging
from pathlib import Path

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_create
from charon.cli.librarian.lifecycle import run_promote
from charon.cli.librarian.permissions import run_permission_change

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Charon.Librarian.Bootstrap")

SKILL_ID = "skill_builder"

PLUGIN_CODE = '''"""
Plugin entrypoint module for skill_builder.
Provides programmatic skill creation and lifecycle management for agents.
"""

import json
from pathlib import Path
from typing import Any, Dict

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_create
from charon.cli.librarian.lifecycle import run_promote
from charon.cli.librarian.permissions import run_permission_change
from charon.config.paths import PKG_STAGED_SKILLS_DIR


def handle_build_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    description = params.get("description", "Agent-generated skill.")
    category = params.get("category", "General")
    actions = params.get("actions", {})
    plugin_code = params.get("plugin_code")

    if not skill_id or not plugin_code:
        return {"status": "error", "message": "Missing required parameters: 'skill_id' or 'plugin_code'."}

    if not isinstance(actions, dict):
        return {"status": "error", "message": "'actions' must be a dictionary mapping action_name to description string."}

    ret = run_create(skill_id=skill_id, category=category)
    if ret != 0:
        return {"status": "error", "message": f"Failed to scaffold staging directory for '{skill_id}'."}

    staged_dir = PKG_STAGED_SKILLS_DIR / skill_id
    staged_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "skill_id": skill_id,
        "version": params.get("version", "1.0.0"),
        "description": description,
        "category": category,
        "author": params.get("author", "The_Engineer"),
        "stage": "Staged",
        "shelf_tags": params.get("shelf_tags", []),
        "system_requirements": params.get("system_requirements", []),
        "supported_actions": actions,
    }

    manifest_path = staged_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    plugin_path = staged_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(plugin_code)

    run_sync()

    return {
        "status": "success",
        "skill_id": skill_id,
        "message": f"Skill '{skill_id}' successfully constructed and placed in staged quarantine.",
    }


def handle_authorize_agent(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    agent_name = params.get("agent_name")

    if not skill_id or not agent_name:
        return {"status": "error", "message": "Missing required parameters: 'skill_id' or 'agent_name'."}

    res = run_permission_change(skill_id=skill_id, agent_name=agent_name, action="grant")
    if res == 0:
        return {"status": "success", "message": f"Granted agent '{agent_name}' access to skill '{skill_id}'."}
    return {"status": "error", "message": f"Failed to grant permission for '{agent_name}' on '{skill_id}'."}


def handle_promote_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = params.get("skill_id")
    if not skill_id:
        return {"status": "error", "message": "Missing required parameter 'skill_id'."}

    res = run_promote(skill_id=skill_id)
    if res == 0:
        return {"status": "success", "skill_id": skill_id, "message": f"Skill '{skill_id}' successfully promoted to dynamic production."}
    return {"status": "error", "message": f"Failed to promote staged skill '{skill_id}'."}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "build_skill":
        return handle_build_skill(params)
    elif action_name == "authorize_agent":
        return handle_authorize_agent(params)
    elif action_name == "promote_skill":
        return handle_promote_skill(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'skill_builder'.")
'''


def bootstrap_meta_skill():
    logger.info(f"1. Scaffolding meta-skill '{SKILL_ID}' in staging...")
    run_create(skill_id=SKILL_ID, category="Meta")

    staged_dir = Path(f"charon/skills/staged/{SKILL_ID}")
    staged_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "skill_id": SKILL_ID,
        "version": "1.0.0",
        "description": "Meta-skill allowing authorized agents to scaffold, write, authorize, and promote new skills programmatically.",
        "category": "Meta",
        "author": "Charon System",
        "stage": "Staged",
        "shelf_tags": ["The_Engineer", "Generalist"],
        "system_requirements": [],
        "supported_actions": {
            "build_skill": "Scaffold and write a new skill manifest and plugin.py implementation into staging.",
            "authorize_agent": "Grant an agent access to a target skill ID.",
            "promote_skill": "Promote a staged skill package into active dynamic production.",
        },
    }

    with open(staged_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    with open(staged_dir / "plugin.py", "w", encoding="utf-8") as f:
        f.write(PLUGIN_CODE)

    logger.info("2. Syncing meta-skill manifest into SQLite...")
    run_sync()

    logger.info("3. Authorizing 'The_Engineer' and 'Generalist'...")
    run_permission_change(skill_id=SKILL_ID, agent_name="The_Engineer", action="grant")
    run_permission_change(skill_id=SKILL_ID, agent_name="Generalist", action="grant")

    logger.info("4. Promoting 'skill_builder' to dynamic production...")
    res = run_promote(skill_id=SKILL_ID)

    if res == 0:
        logger.info("✅ Meta-skill 'skill_builder' successfully installed!")
    else:
        logger.error("❌ Promotion failed.")


if __name__ == "__main__":
    bootstrap_meta_skill()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/bootstrap_task_tracker_skill.py`

```python
"""
scripts/bootstrap_task_tracker_skill.py
Programmatically constructs and promotes task_tracker_manage using Charon Librarian.
"""

import json
import logging
from pathlib import Path

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_create
from charon.cli.librarian.lifecycle import run_promote
from charon.cli.librarian.permissions import run_permission_change

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Charon.Librarian.Bootstrap")

SKILL_ID = "task_tracker_manage"

PLUGIN_CODE = '''"""
Plugin entrypoint module for task_tracker_manage.
Connects agent action invocations to the active TaskTrackerTickerProvider.
"""

import uuid
from typing import Any, Dict
from charon.gateway.ticker.engine import ticker_engine
from charon.gateway.ticker.providers.task_tracker import TaskTrackerTickerProvider, TaskItem


def _get_task_provider() -> TaskTrackerTickerProvider:
    """Retrieve or lazy-instantiate the task tracker provider from the TickerEngine."""
    provider = ticker_engine._providers.get("task_tracker")
    if not provider:
        provider = TaskTrackerTickerProvider()
        ticker_engine.register_provider(provider)
    return provider  # type: ignore


def handle_add_task(params: Dict[str, Any]) -> Dict[str, Any]:
    title = params.get("title")
    if not title:
        return {"status": "error", "message": "Missing required parameter 'title'."}

    priority = params.get("priority", "medium").lower()
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    task_id = params.get("task_id") or f"task-{uuid.uuid4().hex[:6]}"

    provider = _get_task_provider()
    task = TaskItem(
        id=task_id,
        title=title,
        priority=priority,
        pinned=True,
        completed=False,
    )
    provider.add_task(task)

    return {
        "status": "success",
        "task_id": task_id,
        "message": f"Task '{title}' [{priority.upper()}] posted to top bar ticker.",
    }


def handle_complete_task(params: Dict[str, Any]) -> Dict[str, Any]:
    task_id = params.get("task_id")
    if not task_id:
        return {"status": "error", "message": "Missing required parameter 'task_id'."}

    provider = _get_task_provider()
    success = provider.complete_task(task_id)

    if success:
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Task '{task_id}' marked completed and removed from ticker.",
        }
    return {
        "status": "error",
        "message": f"Task '{task_id}' was not found in active ticker memory.",
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "add_task":
        return handle_add_task(params)
    elif action_name == "complete_task":
        return handle_complete_task(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'task_tracker_manage'.")
'''


def bootstrap_skill():
    logger.info(f"1. Scaffolding skill '{SKILL_ID}' in Librarian staging...")
    run_create(skill_id=SKILL_ID, category="System")

    staged_dir = Path(f"charon/skills/staged/{SKILL_ID}")
    staged_dir.mkdir(parents=True, exist_ok=True)

    # Corrected Manifest with stage='Staged' explicit declaration
    manifest_data = {
        "skill_id": SKILL_ID,
        "version": "1.0.0",
        "description": "Allows Charon agents to manage top bar ticker tasks.",
        "category": "System",
        "author": "Charon Librarian",
        "stage": "Staged",
        "shelf_tags": ["tasks", "ticker", "gnome_ui"],
        "system_requirements": [],
        "supported_actions": {
            "add_task": "Add or pin a new task (title, priority, task_id) to the top bar ticker loop.",
            "complete_task": "Mark an existing task_id as completed to remove it from ticker rotation.",
        },
    }

    manifest_path = staged_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Write actual implementation code to plugin.py
    plugin_path = staged_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(PLUGIN_CODE)

    logger.info("2. Syncing updated manifest into SQLite...")
    run_sync()

    logger.info("3. Authorizing skill access for agent 'The_Engineer' and 'Generalist'...")
    run_permission_change(skill_id=SKILL_ID, agent_name="The_Engineer", action="grant")
    run_permission_change(skill_id=SKILL_ID, agent_name="Generalist", action="grant")

    logger.info("4. Promoting skill from staged quarantine -> dynamic production...")
    res = run_promote(skill_id=SKILL_ID)

    if res == 0:
        logger.info("✅ Skill 'task_tracker_manage' successfully installed, authorized, and promoted!")
    else:
        logger.error("❌ Promotion failed.")


if __name__ == "__main__":
    bootstrap_skill()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/bump_version.py`

```python
#!/usr/bin/env python3
"""
scripts/bump_version.py — Automated SemVer bumper, header syncer, and Git tagger.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

from scripts.standardize_headers import main as sync_headers

VERSION_FILE = Path(__file__).resolve().parents[1] / "charon" / "__version__.py"


def parse_version(v_str: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v_str.strip())
    if not match:
        raise ValueError(f"Invalid SemVer string: '{v_str}'")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(part: str) -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise RuntimeError("Could not find __version__ in charon/__version__.py")

    current_str = match.group(1)
    major, minor, patch = parse_version(current_str)

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    new_content = re.sub(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        f'__version__ = "{new_version}"',
        content,
    )
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    return new_version


def main():
    parser = argparse.ArgumentParser(description="Bump Charon SemVer, sync file headers, and optionally Git tag.")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Part of SemVer to bump")
    parser.add_argument("--tag", action="store_true", help="Automatically commit change and create git tag")
    args = parser.parse_args()

    try:
        new_v = bump_version(args.part)
        print(f"Successfully bumped project version to v{new_v}")

        # Sync headers across codebase
        sync_headers()

        if args.tag:
            repo_root = VERSION_FILE.parents[1]
            subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", f"chore(release): bump version to v{new_v}"], cwd=repo_root, check=True)
            subprocess.run(["git", "tag", "-a", f"v{new_v}", "-m", f"Release v{new_v}"], cwd=repo_root, check=True)
            print(f"Created Git commit and tag: v{new_v}")

    except Exception as e:
        print(f"Error bumping version: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/charon_db_admin.py`

```python
#!/usr/bin/env python3
"""
charon_db_admin.py — Consolidated ChromaDB Maintenance & Memory Ledger Utility for Charon.
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

import chromadb

# Resolve default database path (preferring global user path)
XDG_DB_PATH = Path.home() / ".local" / "share" / "charon" / "chroma_db"
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "memory"

DEFAULT_DB_PATH = XDG_DB_PATH if XDG_DB_PATH.exists() else LOCAL_DB_PATH


def resolve_collection(client: chromadb.PersistentClient, target_name: Optional[str] = None):
    """Resolves target collection or falls back to default/first available."""
    collections = client.list_collections()
    if not collections:
        print(f"❌ No vector collections found at path: {client._path}")
        sys.exit(1)

    if target_name:
        try:
            return client.get_collection(target_name)
        except Exception:
            print(f"⚠️ Collection '{target_name}' not found. Available: {[c.name for c in collections]}")
            sys.exit(1)

    # Prefer 'ledger' if present, otherwise default to first available
    for col in collections:
        if col.name.lower() == "ledger":
            return col

    return collections[0]


def list_entries(col, limit: Optional[int] = None):
    """Lists entries in the collection."""
    results = col.get(include=["documents", "metadatas"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])

    total = len(ids)
    display_count = min(limit, total) if limit else total

    print(f"\n📦 Collection: '{col.name}' ({total} total records)\n" + "─" * 70)
    for idx in range(display_count):
        doc_id = ids[idx]
        doc = docs[idx] if docs else ""
        meta = metas[idx] if metas else {}
        print(f"[{doc_id}] {doc[:100]}{'...' if len(doc) > 100 else ''}")
        print(f" └─ Metadata: {meta}")
    print("─" * 70)


def search_entries(col, query: str):
    """Substrings/Fuzzy text search inside stored documents."""
    results = col.get(include=["documents", "metadatas"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])

    matches = [
        (i, d, m) for i, d, m in zip(ids, docs, metas)
        if query.lower() in d.lower()
    ]

    print(f"\n🔍 Found {len(matches)} matching records for query '{query}':\n" + "─" * 70)
    for doc_id, doc, meta in matches:
        print(f"[{doc_id}] {doc}")
        print(f" └─ Metadata: {meta}")
    print("─" * 70)


def prune_duplicates(col, force: bool = False):
    """Scans and prunes duplicate document entries, keeping the first occurrence."""
    results = col.get(include=["documents"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])

    seen_docs = set()
    ids_to_delete: List[str] = []

    for doc_id, doc in zip(ids, docs):
        if doc in seen_docs:
            ids_to_delete.append(doc_id)
        else:
            seen_docs.add(doc)

    if not ids_to_delete:
        print("✨ Ledger is clean. No duplicate documents found.")
        return

    print(f"⚠️ Found {len(ids_to_delete)} duplicate records.")
    if not force:
        confirm = input(f"Remove {len(ids_to_delete)} duplicates? (y/N): ")
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    col.delete(ids=ids_to_delete)
    print(f"✅ Successfully pruned {len(ids_to_delete)} duplicate records.")


def delete_by_id(col, doc_id: str):
    """Deletes a record by exact ID."""
    col.delete(ids=[doc_id])
    print(f"✅ Removed record ID: {doc_id}")


def purge_by_pattern(col, pattern: str, force: bool = False):
    """Deletes all records containing matching substring."""
    results = col.get(include=["documents"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])

    to_delete = [i for i, d in zip(ids, docs) if pattern.lower() in d.lower()]
    if not to_delete:
        print(f"⚠️ No documents matched pattern '{pattern}'.")
        return

    print(f"⚠️ Found {len(to_delete)} records matching pattern '{pattern}'.")
    if not force:
        confirm = input(f"Delete {len(to_delete)} matching records? (y/N): ")
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    col.delete(ids=to_delete)
    print(f"✅ Purged {len(to_delete)} records matching pattern '{pattern}'.")


def purge_all(col, force: bool = False):
    """Wipes all contents of the collection."""
    ids = col.get().get("ids", [])
    if not ids:
        print("Collection is already empty.")
        return

    print(f"🚨 CRITICAL ACTION: About to wipe ALL {len(ids)} records from '{col.name}'!")
    if not force:
        confirm = input("Are you absolutely sure? (y/N): ")
        if confirm.lower() != "y":
            print("Wipe cancelled.")
            return

    col.delete(ids=ids)
    print(f"🧹 Collection '{col.name}' has been completely cleared.")


def main():
    parser = argparse.ArgumentParser(description="Charon Memory Ledger DB Administration Tool")
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH), help="Path to ChromaDB directory")
    parser.add_argument("--collection", "-c", type=str, help="Specific collection name (defaults to 'ledger')")
    parser.add_argument("--list", "-l", action="store_true", help="List stored records")
    parser.add_argument("--limit", type=int, help="Limit output rows for --list")
    parser.add_argument("--search", "-s", type=str, help="Search records containing substring")
    parser.add_argument("--dedupe", action="store_true", help="Scan and prune exact duplicate records")
    parser.add_argument("--delete-id", type=str, help="Delete record by exact ID")
    parser.add_argument("--purge-pattern", type=str, help="Delete all records matching substring")
    parser.add_argument("--wipe-all", action="store_true", help="Wipe entire memory collection")
    parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation prompts")

    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    if not db_path.exists():
        print(f"❌ Specified DB path does not exist: {db_path}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(db_path))
    collection = resolve_collection(client, args.collection)

    if args.list:
        list_entries(collection, limit=args.limit)
    elif args.search:
        search_entries(collection, args.search)
    elif args.dedupe:
        prune_duplicates(collection, force=args.force)
    elif args.delete_id:
        delete_by_id(collection, args.delete_id)
    elif args.purge_pattern:
        purge_by_pattern(collection, args.purge_pattern, force=args.force)
    elif args.wipe_all:
        purge_all(collection, force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/db/bootstrap_agent_roster.py`

```python
"""
charon/db/bootstrap.py
System Version: v0.2.1 | File Revision: 2.0.0

Bootstraps the agent_registry, system_roles, and route_registry schemas
and seeds initial immutable system slots using role-based abstraction.
"""

import logging
from pathlib import Path
from typing import List, Tuple

from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Bootstrap")

# Baseline Bootstrap Agent (Used if agent_registry is completely unpopulated)
CORE_BOOTSTRAP_AGENT_ID = "core_system_agent"

# Mandatory System Roles mapping (Role Name, Search Query / Description)
SYSTEM_ROLE_DEFINITIONS: List[Tuple[str, str, str]] = [
    (
        "default_system_generalist",
        "Generalist",
        "Primary conversational and general execution node.",
    ),
    (
        "default_system_planner",
        "Planner",
        "Primary orchestrator and step-by-step task planner.",
    ),
    (
        "default_system_engineer",
        "Engineer",
        "Diagnostic, repair, and skill-gap resolution agent.",
    ),
    (
        "system_fallback",
        "Generalist",
        "Universal fallback agent when role or route resolution fails.",
    ),
    (
        "system_archivist",
        "Archivist",
        "Core memory, relational storage, and RAG retrieval node.",
    ),
    (
        "system_steward",
        "Steward",
        "OS automation and external system command dispatch node.",
    ),
    (
        "role_quartermaster",
        "Quartermaster",
        "Inventory auditing and resource tracking node.",
    ),
    (
        "role_cleaner",
        "Cleaner",
        "Workspace hygiene and file maintenance node.",
    ),
    (
        "role_spark",
        "Spark",
        "Low-level firmware compilation and hardware build node.",
    ),
    (
        "role_machinist",
        "Machinist",
        "CAD processing and fabrication specification node.",
    ),
    (
        "role_scout",
        "Scout",
        "External web intelligence and scraping node.",
    ),
    (
        "role_overseer",
        "Overseer",
        "System telemetry and event auditing node.",
    ),
]

# Base 11 Seed Mappings (Action Trigger -> Target System Role)
INITIAL_SYSTEM_ROUTES: List[Tuple[str, str, str]] = [
    ("audit_inventory", "role_quartermaster", "Inventory auditing and tracking"),
    ("query_memory", "system_archivist", "Long-term vector and relational memory lookups"),
    ("manage_workspace", "role_cleaner", "Workspace hygiene and temp file cleanup"),
    ("compile_firmware", "role_spark", "Low-level code compilation and hardware build"),
    ("process_cad", "role_machinist", "CAD file conversion and machining specs"),
    ("analyze_roadmap", "default_system_planner", "Strategic project planning and task decomposition"),
    ("execute_diagnostic", "default_system_engineer", "System diagnostic execution and error tracing"),
    ("answer_query", "default_system_generalist", "General reasoning and conversational query handling"),
    ("web_search", "role_scout", "External web scraping and intelligence gathering"),
    ("audit_telemetry", "role_overseer", "Telemetry processing and event auditing"),
    ("transmit_command", "system_steward", "OS automation and external system command dispatch"),
]


def init_route_registry(db_path: Path) -> None:
    """Initializes system schemas and seeds immutable baseline system routes and roles."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 1. Ensure prerequisite tables exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_registry (
        agent_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        description TEXT NOT NULL,
        default_action TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        system_prompt TEXT DEFAULT ''
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_roles (
        role_name TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS route_registry (
        route_id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_trigger TEXT UNIQUE NOT NULL,
        target_role TEXT NOT NULL,
        fallback_role TEXT DEFAULT 'system_fallback',
        route_type TEXT CHECK(route_type IN ('SYSTEM', 'USER_OVERRIDE', 'DYNAMIC_AUTO', 'EPHEMERAL')) NOT NULL DEFAULT 'DYNAMIC_AUTO',
        is_active INTEGER NOT NULL DEFAULT 1,
        description TEXT,
        created_by TEXT DEFAULT 'system',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_count INTEGER DEFAULT 0,
        last_executed_at TIMESTAMP,
        FOREIGN KEY(target_role) REFERENCES system_roles(role_name) ON DELETE RESTRICT,
        FOREIGN KEY(fallback_role) REFERENCES system_roles(role_name) ON DELETE SET NULL
    );
    """)

    # 2. Prevent NOT NULL errors on empty DB: Guarantee baseline agent exists
    cursor.execute("""
    INSERT INTO agent_registry (agent_id, display_name, description, default_action, system_prompt)
    VALUES (?, 'System Core Assistant', 'Fallback execution node for system bootstrap.', 'answer_query', '')
    ON CONFLICT(agent_id) DO NOTHING;
    """, (CORE_BOOTSTRAP_AGENT_ID,))

    # 3. Seed/Update System Roles
    for role_name, match_pattern, desc in SYSTEM_ROLE_DEFINITIONS:
        cursor.execute("""
        INSERT INTO system_roles (role_name, agent_id, description)
        VALUES (
            ?,
            COALESCE(
                (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE ? OR display_name LIKE ?) AND is_active = 1 LIMIT 1),
                (SELECT agent_id FROM agent_registry WHERE is_active = 1 LIMIT 1),
                ?
            ),
            ?
        )
        ON CONFLICT(role_name) DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP,
            agent_id = COALESCE(
                (SELECT agent_id FROM agent_registry WHERE (agent_id LIKE ? OR display_name LIKE ?) AND is_active = 1 LIMIT 1),
                system_roles.agent_id
            );
        """, (
            role_name, f"%{match_pattern}%", f"%{match_pattern}%", CORE_BOOTSTRAP_AGENT_ID, desc,
            f"%{match_pattern}%", f"%{match_pattern}%"
        ))

    # 4. Seed Base 11 Immutable System Routes
    for trigger, target_role, desc in INITIAL_SYSTEM_ROUTES:
        cursor.execute("""
        INSERT INTO route_registry (action_trigger, target_role, fallback_role, route_type, description, created_by)
        VALUES (?, ?, 'system_fallback', 'SYSTEM', ?, 'system_bootstrapper')
        ON CONFLICT(action_trigger) DO UPDATE SET
            target_role = EXCLUDED.target_role,
            fallback_role = EXCLUDED.fallback_role,
            description = EXCLUDED.description,
            route_type = 'SYSTEM';
        """, (trigger, target_role, desc))

    conn.commit()
    conn.close()
    logger.info("Database schema and system routes initialized/seeded successfully.")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/dump_schema_and_manifests.py`

```python
#!/usr/bin/env python3
"""
scripts/dump_schema_and_manifests.py
System Version: v0.6.4 (Read-Only)

Dumps:
1. Current SQLite table schema for 'skill_registry'
2. Raw manifest.json contents for 3 representative skills
"""

import json
import sqlite3
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

SAMPLES = [
    "archivist_datasheet_rag",
    "archivist_vector_ledger",
    "code_python_interpreter",
]


def dump_info():
    print("\n" + "=" * 80)
    print(" 🏛️  1. CURRENT DATABASE SCHEMA (`skill_registry`)")
    print("=" * 80)

    if STATE_DB_PATH.exists():
        conn = sqlite3.connect(str(STATE_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(skill_registry);")
        columns = cursor.fetchall()
        conn.close()

        print(f"{'CID':<5} | {'COLUMN NAME':<25} | {'DATA TYPE':<12} | {'NOT NULL':<8} | {'DEFAULT'}")
        print("-" * 80)
        for col in columns:
            cid, name, type_, notnull, dflt, pk = col
            print(f"{cid:<5} | {name:<25} | {type_:<12} | {notnull:<8} | {dflt}")
    else:
        print(f"⚠️ Database not found at {STATE_DB_PATH}")

    print("\n" + "=" * 80)
    print(" 📄 2. RAW SAMPLE MANIFESTS FROM DISK")
    print("=" * 80)

    for sample in SAMPLES:
        m_path = SKILLS_DIR / sample / "manifest.json"
        print(f"\n--- 📁 {sample}/manifest.json ---")
        if m_path.exists():
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                print(json.dumps(content, indent=2))
            except Exception as e:
                print(f"Error reading JSON: {e}")
        else:
            print("⚠️ File not found.")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    dump_info()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/find_unindexed_skills.py`

```python
#!/usr/bin/env python3
"""
scripts/find_unindexed_skills.py
System Version: v0.6.0

Cross-references physical skill directory names against active/present entries
in skill_registry to report indexed vs. unindexed on-disk skills.
"""

import sqlite3
import sys
from pathlib import Path

# Standard database path fallback
STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()

GROUND_TRUTH_SKILLS = {
    "archivist_datasheet_rag",
    "archivist_vector_ledger",
    "cleaner_cad_sweeper",
    "cleaner_git_manager",
    "cleaner_log_pruner",
    "cleaner_workspace_deleter",
    "cleaner_workspace_inspector",
    "cleaner_workspace_scaffolder",
    "code_python_interpreter",
    "code_sandbox_executor",
    "code_script_generator",
    "code_self_healing_solver",
    "extract_pdf_ocr_skill",
    "fab_cad_tools",
    "fab_cam_slicer",
    "fab_printer_transmitter",
    "generalist_math_evaluator",
    "generalist_query_handler",
    "generalist_rag_synthesizer",
    "generalist_system_executor",
    "generalist_system_inspector",
    "hw_eda_kicad",
    "hw_firmware_pio",
    "iot_home_assistant",
    "iot_mqtt_publisher",
    "kicad_bom_exporter",
    "plan_task_decomposer",
    "quartermaster_bom_auditor",
    "quartermaster_datasheet_fetcher",
    "quartermaster_inventory_manager",
    "skill_builder",
    "sys_asset_pruner",
    "sys_health_auditor",
    "sys_log_analyzer",
    "sys_os_control",
    "task_tracker_manage",
    "web_scraper",
    "web_search",
}


def find_unindexed():
    if not STATE_DB_PATH.exists():
        print(f"Error: Database file not found at {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT skill_id, action_name FROM skill_registry;")
    rows = cursor.fetchall()
    conn.close()

    indexed_in_db = set()
    for s_id, a_name in rows:
        if s_id:
            indexed_in_db.add(s_id)
        if a_name:
            indexed_in_db.add(a_name)

    indexed = GROUND_TRUTH_SKILLS.intersection(indexed_in_db)
    missing = GROUND_TRUTH_SKILLS - indexed_in_db

    print("=" * 65)
    print(f" 🟢 INDEXED SKILLS IN DATABASE ({len(indexed)} / 38)")
    print("=" * 65)
    for skill in sorted(indexed):
        print(f"  [✓] {skill}")

    print("\n" + "=" * 65)
    print(f" 🔴 UNINDEXED / MISSING SKILLS ({len(missing)} / 38)")
    print("=" * 65)
    for skill in sorted(missing):
        print(f"  [✗] {skill}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    find_unindexed()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/generate_notebook_sources.py`

```python
#!/usr/bin/env python3
import datetime
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
OUTPUT_DIR = ROOT / "notebook_sources"
OUTPUT_DIR.mkdir(exist_ok=True)

# Domain targets mapping files, directories, and globs
DOMAINS = {
    "01_Specs_and_Architecture": [
        "*.md",  # Root markdown files (README, CONTEXT, PLANNING, etc.)
        "pyproject.toml",
        "docs"  # All docs/ subdirectories (design, planning, architecture)
    ],
    "02_Core_Engine_and_State": [
        "charon/core"
    ],
    "03_Gateway_CLI_and_IPC": [
        "charon/daemon.py",
        "charon/sdk.py",
        "charon/skill_forge_cli.py",
        "charon/exceptions.py",
        "charon/__version__.py",
        "charon/gateway",
        "charon/cli",
        "charon/telemetry"
    ],
    "04a_Agents_Cognition": [
        "charon/agents/base.py",
        "charon/agents/planner",
        "charon/agents/engineer",
        "charon/agents/generalist",
        "charon/agents/overseer"
    ],
    "04b_Agents_Hardware_CAD": [
        "charon/agents/spark",
        "charon/agents/machinist",
        "charon/agents/steward"
    ],
    "04c_Agents_Operations": [
        "charon/agents/archivist",
        "charon/agents/quartermaster",
        "charon/agents/scout",
        "charon/agents/cleaner"
    ],
    "05_Tools_Config_and_Intent": [
        "charon/tools",
        "charon/intent",
        "charon/config",
        "charon/utils",
        "charon/nodes",
        "scripts"
    ],
    "06_PartVault_Integration": [
        "~/Projects/Tools/PartVault"  # Standalone external application repository
    ]
}

ALLOWED_EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml"}
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", ".idea", "htmlcov",
    ".pytest_cache", "notebook_sources", "logs", "memory",
    ".charon_test_artifacts", "node_modules", "dist", "build"
}


def get_metadata():
    """Fetches git commit, branch, and version string for bundle headers."""
    meta = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": "unknown",
        "branch": "unknown",
        "version": "unknown"
    }

    try:
        meta["commit"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).decode().strip()
        meta["branch"] = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        pass

    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyproject.read_text(encoding="utf-8"))
        if match:
            meta["version"] = match.group(1)

    return meta


def collect_files(target_str):
    """Resolves local, absolute, wildcard, or external home-directory (~/) paths."""
    collected = set()
    raw_path = Path(target_str).expanduser()

    # Handle wildcards (e.g. *.md)
    if "*" in target_str:
        search_root = raw_path.parent if raw_path.is_absolute() else (ROOT / raw_path).parent
        pattern = raw_path.name
        if search_root.exists():
            for p in search_root.glob(pattern):
                if p.is_file() and p.suffix in ALLOWED_EXTENSIONS:
                    collected.add(p)
        return collected

    target_path = raw_path if raw_path.is_absolute() else (ROOT / target_str).resolve()

    if not target_path.exists():
        print(f"  [Warning] Path not found: {target_str} (resolved to {target_path})")
        return collected

    if target_path.is_file():
        if target_path.suffix in ALLOWED_EXTENSIONS:
            return {target_path}
        return collected

    # Recurse through target directory
    for root, dirs, filenames in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            file_path = Path(root) / f
            if file_path.suffix in ALLOWED_EXTENSIONS and not f.startswith("."):
                collected.add(file_path)

    return collected


def get_language_tag(suffix):
    """Maps file extensions to Markdown code block language identifiers."""
    if suffix == ".py":
        return "python"
    elif suffix in {".yml", ".yaml"}:
        return "yaml"
    elif suffix == ".toml":
        return "toml"
    return "markdown"


def main():
    print("🚀 Bundling Charon codebase & PartVault integration into NotebookLM sources...")
    meta = get_metadata()
    processed_files = set()

    for domain_name, targets in DOMAINS.items():
        outfile = OUTPUT_DIR / f"{domain_name}.md"
        print(f"\nProcessing domain: {domain_name}")

        domain_files = set()
        for target in targets:
            domain_files.update(collect_files(target))

        new_files = sorted(domain_files - processed_files)
        file_count = 0

        with open(outfile, "w", encoding="utf-8") as out:
            out.write(f"# Subsystem Domain Context: {domain_name}\n")
            out.write(f"> **Generated:** {meta['timestamp']}  \n")
            out.write(f"> **Charon Core Version:** v{meta['version']}  \n")
            out.write(f"> **Git Branch:** `{meta['branch']}` | **Commit:** `{meta['commit']}`\n\n")
            out.write("---\n\n")

            for file_path in new_files:
                try:
                    content = file_path.read_text(encoding="utf-8")

                    # Display path relative to ROOT if internal, else display absolute path
                    try:
                        display_path = file_path.relative_to(ROOT)
                    except ValueError:
                        display_path = file_path

                    out.write(f"## Target File: `{display_path}`\n\n")

                    lang = get_language_tag(file_path.suffix)
                    out.write(f"```{lang}\n{content}\n```\n\n")
                    out.write("─" * 80 + "\n\n")

                    file_count += 1
                    processed_files.add(file_path)
                except Exception as e:
                    print(f"  Failed reading {file_path}: {e}")

        print(f"  Created {outfile.name} ({file_count} files included)")

    # Repository-wide catch-all for any missed local Charon files
    all_repo_files = set()
    for root, dirs, filenames in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            file_path = Path(root) / f
            if file_path.suffix in ALLOWED_EXTENSIONS and not f.startswith("."):
                all_repo_files.add(file_path)

    uncategorized = sorted(all_repo_files - processed_files)
    if uncategorized:
        print(f"\n⚠️ Found {len(uncategorized)} unassigned files! Bundling into 99_Uncategorized.md...")
        outfile = OUTPUT_DIR / "99_Uncategorized.md"
        with open(outfile, "w", encoding="utf-8") as out:
            out.write(f"# Subsystem Domain Context: 99_Uncategorized\n")
            out.write(f"> **Commit:** `{meta['commit']}` | **Version:** v{meta['version']}\n\n---\n\n")
            for file_path in uncategorized:
                content = file_path.read_text(encoding="utf-8")
                lang = get_language_tag(file_path.suffix)
                out.write(
                    f"## Target File: `{file_path.relative_to(ROOT)}`\n\n```{lang}\n{content}\n```\n\n" + "─" * 80 + "\n\n")
                processed_files.add(file_path)

    print(f"\n✨ Done! Source bundles saved to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/inspect_skill_manifests.py`

```python
#!/usr/bin/env python3
"""
scripts/inspect_skill_manifests.py
System Version: v0.6.3 (Read-Only)

Pass 1 Manifest Auditor:
Scans all 38 skill directories on disk, parses manifest.json files, inspects
metadata structure (actions, parameters, schemas), and reports missing/incomplete fields
without modifying state.db.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.ManifestInspector")


def inspect_manifests():
    if not SKILLS_DIR.exists():
        logger.error(f"Directory not found: {SKILLS_DIR}")
        return

    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]

    print("\n" + "=" * 90)
    print(f" 🔍 PASS 1: MANIFEST INSPECTION REPORT ({len(skill_folders)} Directories Found)")
    print("=" * 90 + "\n")

    total_actions_found = 0
    anomalies: List[Dict[str, Any]] = []
    parsed_skills: List[Dict[str, Any]] = []

    for folder in sorted(skill_folders):
        folder_name = folder.name
        manifest_path = folder / "manifest.json"
        plugin_path = folder / "plugin.py"

        folder_info = {
            "folder": folder_name,
            "has_manifest": manifest_path.exists(),
            "has_plugin": plugin_path.exists(),
            "actions": [],
            "warnings": [],
        }

        if not manifest_path.exists():
            folder_info["warnings"].append("Missing manifest.json")
            anomalies.append(folder_info)
            continue

        if not plugin_path.exists():
            folder_info["warnings"].append("Missing plugin.py")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Determine manifest schema type (top-level vs actions array)
            raw_actions = []
            if "actions" in data and isinstance(data["actions"], list):
                raw_actions = data["actions"]
            elif "action_name" in data or "name" in data:
                raw_actions = [data]
            else:
                folder_info["warnings"].append(
                    "Unrecognized schema format (no 'actions' list or 'action_name' root key)")

            for idx, act in enumerate(raw_actions):
                action_name = act.get("action_name") or act.get("name") or "UNNAMED_ACTION"
                skill_id = act.get("skill_id") or f"sk_{action_name}"
                description = act.get("description", "").strip()
                params = act.get("parameters", {})
                version = act.get("version", data.get("version", "N/A"))
                category = act.get("category", data.get("category", "Uncategorized"))

                action_meta = {
                    "skill_id": skill_id,
                    "action_name": action_name,
                    "version": version,
                    "category": category,
                    "desc_len": len(description),
                    "param_count": len(params.get("properties", params)) if isinstance(params, dict) else 0,
                    "has_desc": bool(description),
                }

                # Missing field checks
                missing_fields = []
                if not action_name or action_name == "UNNAMED_ACTION":
                    missing_fields.append("action_name")
                if not description:
                    missing_fields.append("description")
                if not params:
                    missing_fields.append("parameters")

                if missing_fields:
                    folder_info["warnings"].append(f"Action '{action_name}' missing: {', '.join(missing_fields)}")

                folder_info["actions"].append(action_meta)
                total_actions_found += 1

        except json.JSONDecodeError as e:
            folder_info["warnings"].append(f"Invalid JSON format: {e}")
        except Exception as e:
            folder_info["warnings"].append(f"Unexpected error: {e}")

        if folder_info["warnings"]:
            anomalies.append(folder_info)

        parsed_skills.append(folder_info)

    # Output Detailed Breakdown Table
    print(f"{'FOLDER NAME':<33} | {'ACTIONS':<8} | {'PLUGIN?':<8} | {'STATUS / WARNINGS'}")
    print("-" * 90)

    for item in parsed_skills:
        f_name = item["folder"]
        act_cnt = len(item["actions"])
        has_p = "Yes" if item["has_plugin"] else "NO"
        warn_str = " OK" if not item["warnings"] else f"⚠️ {'; '.join(item['warnings'])}"

        print(f"{f_name:<33} | {act_cnt:<8} | {has_p:<8} | {warn_str}")

    print("-" * 90)
    print("\n" + "=" * 90)
    print(" 📊 METADATA SUMMARY & AUDIT TOTALS")
    print("=" * 90)
    print(f" Total Skill Directories Scanned : {len(skill_folders)}")
    print(f" Total Discrete Actions Discovered: {total_actions_found}")
    print(f" Folders With Schema Warnings    : {len(anomalies)}")
    print("=" * 90 + "\n")

    if anomalies:
        print("🚨 DETAILED ANOMALY / INCOMPLETE FIELD REPORT:")
        print("-" * 90)
        for a in anomalies:
            print(f" Folder: {a['folder']}")
            for w in a["warnings"]:
                print(f"  └── ⚠️  {w}")
        print("-" * 90 + "\n")


if __name__ == "__main__":
    inspect_manifests()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/inspect_skill_permission_model.py`

```python
import sqlite3
from pathlib import Path

# Adjust path to your Charon SQLite DB if necessary
db_path = Path("charon/data/charon.db")

if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Database Tables:", tables)

    # Inspect schema for permission-related tables
    for table in tables:
        tname = table[0]
        if "agent" in tname or "skill" in tname or "perm" in tname:
            print(f"\n--- Schema for {tname} ---")
            cursor.execute(f"PRAGMA table_info({tname});")
            for col in cursor.fetchall():
                print(col)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/map_dependencies.py`

```python
#!/usr/bin/env python3
import ast
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
CHARON_DIR = ROOT_DIR / "charon"


def get_imports_from_file(filepath: Path) -> set[str]:
    """Parses a Python file using AST to extract internal `charon` imports."""
    imports = set()
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("charon"):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("charon"):
                imports.add(node.module)

    return imports


def module_path_to_relative(mod_str: str) -> str:
    """Converts a module string (e.g. charon.core.engine) to relative path format."""
    return mod_str.replace(".", "/") + ".py"


def main():
    graph = defaultdict(set)
    all_files = list(CHARON_DIR.rglob("*.py"))

    # Map file relative path -> internal imported modules
    for filepath in all_files:
        rel_path = str(filepath.relative_to(ROOT_DIR))
        imported_mods = get_imports_from_file(filepath)

        for mod in imported_mods:
            # Map module back to relative file path if it exists
            target_rel = module_path_to_relative(mod)
            if (ROOT_DIR / target_rel).exists():
                graph[rel_path].add(target_rel)
            else:
                # Check if it's a directory package (__init__.py)
                dir_target = mod.replace(".", "/") + "/__init__.py"
                if (ROOT_DIR / dir_target).exists():
                    graph[rel_path].add(dir_target)

    print("=" * 60)
    print("CHARON CODEBASE DEPENDENCY MAP")
    print("=" * 60)

    for source, targets in sorted(graph.items()):
        if targets:
            print(f"\n📄 {source}")
            for t in sorted(targets):
                print(f"   └──> {t}")

    # Circular Dependency Check
    print("\n" + "=" * 60)
    print("CIRCULAR DEPENDENCY CHECK")
    print("=" * 60)
    circular_found = False
    for source, targets in graph.items():
        for target in targets:
            if source in graph.get(target, set()):
                print(f"⚠️ CIRCULAR DEPENDENCY: {source} <---> {target}")
                circular_found = True

    if not circular_found:
        print("✅ No direct circular dependencies detected across charon/")

    # Generate Mermaid Diagram
    print("\n" + "=" * 60)
    print("MERMAID.JS DIAGRAM (Copy into Markdown viewer or PyCharm Preview)")
    print("=" * 60)
    print("```mermaid")
    print("graph TD")
    for source, targets in sorted(graph.items()):
        src_clean = source.replace("charon/", "").replace(".py", "").replace("/", "_")
        for target in sorted(targets):
            tgt_clean = (
                target.replace("charon/", "").replace(".py", "").replace("/", "_")
            )
            print(f"    {src_clean} --> {tgt_clean}")
    print("```\n")


if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/migrate_schema.py`

```python
#!/usr/bin/env python3
import json
import logging
import sqlite3
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("Charon.Migration")

DB_PATH = Path.home() / ".local" / "share" / "charon" / "charon_state.db"


def migrate_database():
    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return

    logger.info(f"Connecting to database at {DB_PATH}")

    # Connect with dictionary-like row access
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Enable foreign keys (though we will turn them off briefly for the table swap)
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # ---------------------------------------------------------
        # 1. Clean Up Redundant Tables
        # ---------------------------------------------------------
        logger.info("Dropping redundant 'agents' table...")
        cursor.execute("DROP TABLE IF EXISTS agents;")

        # ---------------------------------------------------------
        # 2. Rebuild skill_registry & Populate agent_skill_map
        # ---------------------------------------------------------
        logger.info("Rebuilding 'skill_registry' and extracting manifest data...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_registry_new (
                action_name TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                category TEXT DEFAULT 'General',
                description TEXT NOT NULL DEFAULT '',
                parameters TEXT DEFAULT '{}',
                system_requirements TEXT NOT NULL DEFAULT '[]',
                consumed_artifacts TEXT NOT NULL DEFAULT '[]',
                produced_artifacts TEXT NOT NULL DEFAULT '[]',
                entry_file_path TEXT NOT NULL,
                handler_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_global INTEGER DEFAULT 0,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Fetch all existing skills
        cursor.execute("SELECT * FROM skill_registry;")
        existing_skills = cursor.fetchall()

        for skill in existing_skills:
            action_name = skill["action_name"]
            manifest_raw = skill["manifest_json"]

            # Parse manifest_json to determine global status and specific shelf tags
            is_global = 0
            shelf_tags = []

            if manifest_raw:
                try:
                    manifest_data = json.loads(manifest_raw)
                    shelf_tags = manifest_data.get("shelf_tags", [])
                    primary_agent = manifest_data.get("primary_agent_id")

                    if primary_agent and primary_agent not in shelf_tags:
                        shelf_tags.append(primary_agent)

                    if "*" in shelf_tags:
                        is_global = 1
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse manifest JSON for action '{action_name}'. Defaulting to global.")
                    is_global = 1

            # Insert into the new refined table
            cursor.execute("""
                INSERT INTO skill_registry_new (
                    action_name, skill_id, version, category, description, 
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, 
                    is_active, is_global, indexed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_name, skill["skill_id"], skill["version"], skill["category"],
                skill["description"], skill["parameters"], skill["system_requirements"],
                skill["consumed_artifacts"], skill["produced_artifacts"],
                skill["entry_file_path"], skill["handler_name"], skill["is_active"],
                is_global, skill["indexed_at"], skill["updated_at"]
            ))

            # Populate agent_skill_map for non-global agents explicitly listed
            if not is_global:
                for tag in shelf_tags:
                    if tag != "*":
                        cursor.execute("""
                            INSERT OR IGNORE INTO agent_skill_map (agent_id, action_name) 
                            VALUES (?, ?)
                        """, (tag, action_name))

        # Swap the skills tables
        cursor.execute("DROP TABLE skill_registry;")
        cursor.execute("ALTER TABLE skill_registry_new RENAME TO skill_registry;")
        cursor.execute("CREATE INDEX idx_skill_registry_action ON skill_registry(action_name);")

        # ---------------------------------------------------------
        # 3. Upgrade system_roles to use RESTRICT
        # ---------------------------------------------------------
        logger.info("Upgrading 'system_roles' table constraints...")

        cursor.execute("""
            CREATE TABLE system_roles_new (
                role_name TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(agent_id) REFERENCES agent_registry(agent_id) ON DELETE RESTRICT
            );
        """)

        # Copy existing roles
        cursor.execute("INSERT INTO system_roles_new SELECT * FROM system_roles;")

        # Swap the roles tables
        cursor.execute("DROP TABLE system_roles;")
        cursor.execute("ALTER TABLE system_roles_new RENAME TO system_roles;")
        cursor.execute("CREATE INDEX idx_system_roles_agent ON system_roles(agent_id);")

        # ---------------------------------------------------------
        # Commit & Re-enable Pragmas
        # ---------------------------------------------------------
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        logger.info("Migration completed successfully. The database schema is now unified.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}. Changes rolled back.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/overseer_runner.py`

```python
"""
scripts/overseer_runner.py — Standalone script for background systemd maintenance.
Executes non-blocking maintenance tasks managed by TheOverseer.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure root Charon directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charon.agents.overseer import TheOverseer

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [OVERSEER-CRON] %(message)s",
)
logger = logging.getLogger("Charon.OverseerRunner")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Charon Overseer Maintenance Runner")
    parser.add_argument(
        "--action",
        type=str,
        default="run_full_maintenance",
        choices=[
            "optimize_databases",
            "audit_vector_store",
            "prune_logs_and_cache",
            "prune_orphaned_assets",
            "audit_resource_guard",
            "get_system_health",
            "resolve_skill_gaps",
            "run_full_maintenance",
        ],
        help="Maintenance action to execute.",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=7,
        help="Age threshold in days for pruning stale logs and cache.",
    )
    parser.add_argument(
        "--target-db",
        type=str,
        default=None,
        help="Optional specific database file or directory path.",
    )

    args = parser.parse_args()

    logger.info(f"Initiating background maintenance task: '{args.action}'")
    overseer = TheOverseer()

    params = {
        "prune_days": args.prune_days,
        "target_db": args.target_db,
    }

    try:
        res = overseer.execute(args.action, params)
        if asyncio.iscoroutine(res):
            res = await res
        logger.info("Maintenance run completed successfully.")
        logger.info(f"Result summary:\n{res}")
    except Exception as e:
        logger.error(f"Overseer background task failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/preview_mainifest_indexing.py`

```python
#!/usr/bin/env python3
"""
scripts/preview_manifest_indexing.py
System Version: v0.6.5 (Read-Only Preview)

Parses all 38 skill manifests using supported_actions, applies DB field mappings,
and prints the resulting action table to verify everything before writing to state.db.
"""

import json
from pathlib import Path

SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def preview_indexing():
    if not SKILLS_DIR.exists():
        print(f"Error: Directory not found at {SKILLS_DIR}")
        return

    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]
    all_actions = []

    for folder in sorted(skill_folders):
        manifest_path = folder / "manifest.json"
        plugin_path = folder / "plugin.py"

        if not manifest_path.exists() or not plugin_path.exists():
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            version = data.get("version", "1.0.0")
            category = data.get("category", "General")
            sys_reqs = json.dumps(data.get("system_requirements", []))
            supported_actions = data.get("supported_actions", {})

            for action_name, action_meta in supported_actions.items():
                skill_id = f"sk_{action_name}"
                description = action_meta.get("description", "").strip()
                parameters = json.dumps(action_meta.get("parameters", {}))
                handler_name = action_name  # Standard handler naming convention

                all_actions.append({
                    "skill_id": skill_id,
                    "action_name": action_name,
                    "folder": folder.name,
                    "version": version,
                    "category": category,
                    "description": description[:50] + "..." if len(description) > 50 else description,
                    "entry_file_path": str(plugin_path),
                    "handler_name": handler_name,
                })

        except Exception as e:
            print(f"⚠️ Error parsing {manifest_path}: {e}")

    print("\n" + "=" * 95)
    print(f" 📑 DISCOVERED ACTIONS PREVIEW ({len(all_actions)} Total Actions Across 38 Folders)")
    print("=" * 95)
    print(f"{'SKILL ID':<28} | {'ACTION NAME':<25} | {'CATEGORY':<20} | {'FOLDER'}")
    print("-" * 95)

    for act in all_actions:
        print(f"{act['skill_id']:<28} | {act['action_name']:<25} | {act['category']:<20} | {act['folder']}")

    print("-" * 95)
    print(f"\nTotal actions to be indexed into skill_registry: {len(all_actions)}\n")


if __name__ == "__main__":
    preview_indexing()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/relink_agent_skills_by_path.py`

```python
#!/usr/bin/env python3
"""
scripts/relink_agent_skills_by_path.py

Rebuilds `agent_skill_map` by matching skill folders inside each agent's
staging directory to the `entry_file_path` column in `skill_registry`.
"""

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
CHARON_ROOT = Path("~/Projects/Tools/Charon/charon").expanduser()
AGENTS_DIR = CHARON_ROOT / "agents_delete"


def relink_agent_skills():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    if not AGENTS_DIR.exists():
        print(f"❌ Agents directory not found at: {AGENTS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🛠️ REBUILDING `agent_skill_map` VIA STAGING & ENTRY FILE PATHS")
    print("=" * 70)

    # 1. Map skill folders in DB to their respective skill_ids via entry_file_path
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry;")
    skill_rows = cursor.fetchall()

    folder_to_skill_ids = defaultdict(list)
    for skill_id, entry_file_path in skill_rows:
        if entry_file_path:
            folder_name = Path(entry_file_path).parent.name
            folder_to_skill_ids[folder_name].append(skill_id)

    print(f" ℹ️ DB holds {len(skill_rows)} total skills across {len(folder_to_skill_ids)} unique skill folders.")

    # 2. Fetch existing mappings to prevent any duplicates
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())
    print(f" ℹ️ Found {len(existing_mappings)} pre-existing mapping(s) in `agent_skill_map`.")

    # 3. Scan agents directory and match staging folders
    discovered_mappings = set()
    agents_processed = 0

    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue

        staging_dir = agent_dir / "staging"
        if not staging_dir.exists():
            continue

        # Resolve normalized agent_id from spec if available, fallback to folder name
        agent_id = agent_dir.name
        spec_file = staging_dir / "agent_spec.json"
        if spec_file.exists():
            try:
                spec_data = json.loads(spec_file.read_text(encoding="utf-8"))
                agent_id = spec_data.get("agent_id", agent_id)
            except Exception:
                pass

        agents_processed += 1
        agent_linked_count = 0

        # Scan subdirectories inside staging/
        for skill_folder in staging_dir.iterdir():
            if skill_folder.is_dir():
                folder_name = skill_folder.name

                # Match staging folder name against skill_registry folder paths
                matched_skill_ids = folder_to_skill_ids.get(folder_name, [])
                for skill_id in matched_skill_ids:
                    discovered_mappings.add((agent_id, skill_id))
                    agent_linked_count += 1

        print(f"  • Agent [{agent_id}]: Matched {agent_linked_count} skill action bindings.")

    # 4. Deduplicate against current DB state
    new_mappings = discovered_mappings - existing_mappings

    # 5. Insert recovered mappings
    if new_mappings:
        cursor.executemany("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, list(new_mappings))
        conn.commit()

    # 6. Final Status Audit
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print(f" 👥 Agents Scanned       : {agents_processed}")
    print(f" ➕ New Mappings Added  : {len(new_mappings)}")
    print(f" ✅ Total Valid Mappings: {total_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    relink_agent_skills()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/remediate_spec_drift.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/repair_agent_skill_map.py`

```python
#!/usr/bin/env python3
"""
scripts/repair_agent_skill_map.py
System Version: v0.6.7

Cleans orphaned skill mappings from agent_skill_map and resyncs
agent assignments from active manifests in skill_registry.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def repair_and_resync_agent_map():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🧹 REPAIRING & RESYNCING `agent_skill_map`")
    print("=" * 70)

    # Step 1: Prune Orphaned Mappings
    cursor.execute("""
        DELETE FROM agent_skill_map 
        WHERE skill_id NOT IN (SELECT skill_id FROM skill_registry);
    """)
    pruned_count = cursor.rowcount
    print(f" 🗑️  Pruned {pruned_count} orphaned records from `agent_skill_map`.")

    # Step 2: Scan Manifests for Declared Agent Assignments
    new_mappings = []
    if SKILLS_DIR.exists():
        for m_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                skill_id = data.get("skill_id", m_path.parent.name)

                # Check for agent metadata key
                assigned_agent = (
                        data.get("agent_id")
                        or data.get("assigned_agent")
                        or data.get("target_agent")
                        or data.get("agent")
                )

                if assigned_agent:
                    # Confirm agent exists in agent_registry
                    cursor.execute(
                        "SELECT 1 FROM agent_registry WHERE agent_id = ?;", (assigned_agent,)
                    )
                    if cursor.fetchone():
                        # Confirm skill is in skill_registry
                        cursor.execute(
                            "SELECT 1 FROM skill_registry WHERE skill_id = ?;", (skill_id,)
                        )
                        if cursor.fetchone():
                            new_mappings.append((assigned_agent, skill_id))
            except Exception as e:
                print(f" ⚠️ Warning reading {m_path}: {e}")

    # Step 3: Insert Valid Manifest Mappings
    inserted_count = 0
    for agent_id, skill_id in new_mappings:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, (agent_id, skill_id))
        if cursor.rowcount > 0:
            inserted_count += 1

    conn.commit()

    # Step 4: Final Count
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_valid_mappings = cursor.fetchone()[0]

    print(f" ➕ Inserted {inserted_count} manifest-declared mappings.")
    print(f" ✅ Total Valid Mappings in DB: {total_valid_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    repair_and_resync_agent_map()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/restore_missing_sources.py`

```python
import argparse
import re
from pathlib import Path

def parse_and_restore(sources_dir: Path, dry_run: bool = True):
    if not sources_dir.exists():
        print(f"❌ Error: Directory '{sources_dir}' not found.")
        return

    md_files = sorted(list(sources_dir.glob("*.md")))
    if not md_files:
        print(f"❌ No .md files found in '{sources_dir}'.")
        return

    print(f"🔍 Found {len(md_files)} markdown bundle(s) in '{sources_dir}'.")
    if dry_run:
        print("⚠️  DRY RUN MODE ENABLED — No files will be created or modified on disk.\n")
    else:
        print("🚀 LIVE RESTORE MODE — Recovering missing files...\n")

    # Regex matches: ## Target File: `filepath` followed by ```lang ... ```
    pattern = re.compile(
        r"## Target File:\s*[`'\"]?(?P<filepath>[^`'\"]+?)[`'\"]?\s*\n+"
        r"```[a-zA-Z0-9_-]*\n"
        r"(?P<code>.*?)"
        r"\n```",
        re.MULTILINE | re.DOTALL
    )

    restored_count = 0
    skipped_count = 0

    for md_file in md_files:
        print(f"--- Scanning {md_file.name} ---")
        text = md_file.read_text(encoding="utf-8", errors="ignore")

        matches = list(pattern.finditer(text))
        if not matches:
            print("  (No target files matched in this bundle)")
            continue

        for match in matches:
            rel_path = match.group("filepath").strip()
            code = match.group("code")
            target_file = Path(rel_path)

            # 🔒 HARD SAFEGUARD: Never touch a file that exists on disk
            if target_file.exists():
                print(f"  [PRESERVED] Existing file protected: {target_file}")
                skipped_count += 1
                continue

            if dry_run:
                print(f"  [WOULD RESTORE] Missing file: {target_file}")
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(code + "\n", encoding="utf-8")
                print(f"  [RESTORED] Recreated missing file: {target_file}")

            restored_count += 1

    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"  • Existing files protected (skipped): {skipped_count}")
    if dry_run:
        print(f"  • Missing files identified for restore: {restored_count}")
        print("\n💡 To write missing files to disk, run with `--live`:")
        print("   python restore_missing_sources.py --live")
    else:
        print(f"  • Missing files successfully restored: {restored_count}")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safely restore missing Charon files from notebook bundles.")
    parser.add_argument("--live", action="store_true", help="Execute live restoration (default is dry-run)")
    parser.add_argument("--dir", default="notebook_sources", help="Path to notebook sources directory")
    args = parser.parse_args()

    parse_and_restore(Path(args.dir), dry_run=not args.live)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/save/populate_agent_skill_map.py`

```python
#!/usr/bin/env python3
"""
scripts/populate_agent_skill_map.py

Exact mapping:
1. Agent ID = folder name in charon/agents_delete/
2. Skill Folder = subfolder in charon/agents_delete/<agent_id>/staging/skills/
3. Skill ID = matches folder name in skill_registry.entry_file_path
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
CHARON_ROOT = Path("/charon").expanduser()
LEGACY_AGENTS_DIR = CHARON_ROOT / "agents_delete"


def populate():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🛠️ POPULATING `agent_skill_map` (EXACT MATCH)")
    print("=" * 70)

    # 1. Load exact valid agent IDs from agent_registry
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    # 2. Map skill folder names to skill_ids via entry_file_path in skill_registry
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry;")
    folder_to_skills = defaultdict(list)
    for skill_id, entry_path in cursor.fetchall():
        if entry_path:
            folder_name = Path(entry_path).parent.name
            folder_to_skills[folder_name].append(skill_id)

    # 3. Load existing mappings to prevent duplication
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())

    print(f" ℹ️ DB holds {len(valid_agents)} Agents and {len(folder_to_skills)} Skill Folders.")
    print(f" ℹ️ Existing mappings in `agent_skill_map`: {len(existing_mappings)}")

    new_mappings = set()

    # 4. Scan agents_delete directories directly
    for agent_dir in sorted(LEGACY_AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue

        agent_id = agent_dir.name  # Exact match to agent_registry (e.g., 'archivist')
        if agent_id not in valid_agents:
            continue

        skills_dir = agent_dir / "staging" / "skills"
        if not skills_dir.exists():
            continue

        agent_count = 0
        for skill_folder in skills_dir.iterdir():
            if not skill_folder.is_dir():
                continue

            folder_name = skill_folder.name
            matched_skill_ids = folder_to_skills.get(folder_name, [])

            for skill_id in matched_skill_ids:
                mapping_pair = (agent_id, skill_id)
                if mapping_pair not in existing_mappings:
                    new_mappings.add(mapping_pair)
                    agent_count += 1

        print(f"  • Agent [{agent_id}]: Queued {agent_count} new skill mapping(s)")

    # 5. Insert new unique mappings
    if new_mappings:
        cursor.executemany("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, list(new_mappings))
        conn.commit()

    # 6. Report final database status
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_count = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print(f" ➕ New Mappings Added  : {len(new_mappings)}")
    print(f" ✅ Total Valid Mappings: {total_count}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    populate()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/seed_skill_permissions.py`

```python
#!/usr/bin/env python3
import sqlite3
import os
from pathlib import Path

DB_PATH = os.path.expanduser("~/.local/share/charon/charon_state.db")

# Keyword heuristics for matching skills to permission primitives
HEURISTICS = {
    "sys:shell_exec": ["exec", "shell", "bash", "terminal", "command", "run_script", "process", "cli"],
    "net:http_request": ["http", "web", "url", "api", "fetch", "download", "scrape", "search", "request"],
    "fs:write_file": ["write", "save", "create_file", "append", "edit_file", "output_file", "store"],
    "fs:read_file": ["read", "cat", "get_file", "load", "parse", "view", "inspect", "search_file"]
}

def seed_skill_permissions():
    if not Path(DB_PATH).exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch all active skills
    cursor.execute("SELECT skill_id, action_name, category, description FROM skill_registry;")
    skills = cursor.fetchall()

    mapped_count = 0
    assigned_permissions = 0

    for skill_id, action_name, category, description in skills:
        text_corpus = f"{action_name} {category} {description}".lower()
        matched_perms = set()

        for perm_id, keywords in HEURISTICS.items():
            if any(kw in text_corpus for kw in keywords):
                matched_perms.add(perm_id)

        # Baseline fallback: If no keyword matched, assign standard read access
        if not matched_perms:
            matched_perms.add("fs:read_file")

        # Insert skill permission mappings
        for perm_id in matched_perms:
            cursor.execute("""
                INSERT OR IGNORE INTO skill_permissions (skill_id, perm_id)
                VALUES (?, ?);
            """, (skill_id, perm_id))
            assigned_permissions += 1

        mapped_count += 1

    conn.commit()
    conn.close()

    print(f"Successfully processed {mapped_count} skills and seeded {assigned_permissions} permission bindings.")

if __name__ == "__main__":
    seed_skill_permissions()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/surgical_recover_agent_skill_map.py`

```python
#!/usr/bin/env python3
"""
scripts/surgical_recover_agent_skill_map.py

Non-destructive recovery tool for agent_skill_map.
Scans disk manifests and agent specs to restore capability links into SQLite.
Guarantees zero duplication of existing mappings.
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
CHARON_ROOT = Path("~/Projects/Tools/Charon/charon").expanduser()
SKILLS_DIR = CHARON_ROOT / "storage" / "dynamic"
AGENTS_DIR = CHARON_ROOT / "agents"


def recover_agent_skill_map():
    if not DB_PATH.exists():
        print(f"❌ DB not found at: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print(" 🩹 SURGICAL RECOVERY: `agent_skill_map`")
    print("=" * 70)

    # 1. Fetch existing state from DB (Read-Only)
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT skill_id, action_name FROM skill_registry;")
    skill_rows = cursor.fetchall()
    valid_skills = {row[0] for row in skill_rows}
    action_to_skill = {row[1]: row[0] for row in skill_rows}

    # Fetch existing mappings to prevent any duplicates
    cursor.execute("SELECT agent_id, skill_id FROM agent_skill_map;")
    existing_mappings = set(cursor.fetchall())

    print(f" ℹ️ DB holds {len(valid_agents)} Agents and {len(valid_skills)} Skills.")
    print(f" ℹ️ Found {len(existing_mappings)} existing mapping(s) in `agent_skill_map`.")

    scanned_mappings = set()

    # 2. PASS A: Scan Agent Specs (Agent -> Skills/Actions)
    if AGENTS_DIR.exists():
        for spec_path in AGENTS_DIR.rglob("*.json"):
            try:
                data = json.loads(spec_path.read_text(encoding="utf-8"))
                agent_id = data.get("agent_id")
                if not agent_id or agent_id not in valid_agents:
                    continue

                declared_items = []
                for key in ("skills", "actions", "capabilities", "equipped_skills"):
                    val = data.get(key)
                    if isinstance(val, list):
                        declared_items.extend(val)

                for item in declared_items:
                    if item in valid_skills:
                        scanned_mappings.add((agent_id, item))
                    elif item in action_to_skill:
                        scanned_mappings.add((agent_id, action_to_skill[item]))

            except Exception as e:
                print(f" ⚠️ Warning reading agent spec {spec_path}: {e}")

    # 3. PASS B: Scan Skill Manifests (Skill -> Agent)
    if SKILLS_DIR.exists():
        for manifest_path in SKILLS_DIR.glob("*/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                skill_id = data.get("skill_id", manifest_path.parent.name)

                if skill_id not in valid_skills:
                    continue

                agent_refs = []
                for key in ("agent_id", "assigned_agent", "target_agent", "agent", "role"):
                    val = data.get(key)
                    if isinstance(val, str):
                        agent_refs.append(val)
                    elif isinstance(val, list):
                        agent_refs.extend(val)

                for a_id in agent_refs:
                    if a_id in valid_agents:
                        scanned_mappings.add((a_id, skill_id))

            except Exception as e:
                print(f" ⚠️ Warning reading skill manifest {manifest_path}: {e}")

    # 4. Filter out any mapping that already exists in the table
    new_mappings = scanned_mappings - existing_mappings

    if not new_mappings:
        print(" ✨ No new unique mappings found to insert.")
    else:
        # Safely insert only genuinely new bindings
        for agent_id, skill_id in new_mappings:
            cursor.execute("""
                INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?);
            """, (agent_id, skill_id))

        conn.commit()

    # 5. Report Final State
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    print(f" ➕ Inserted {len(new_mappings)} new unique map records.")
    print(f" ✅ Total Active Mappings in DB: {total_mappings}")
    print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    recover_agent_skill_map()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/sync_agent_skill_map_from_legacy.py`

```python
#!/usr/bin/env python3
"""
scripts/sync_agent_skill_map_from_legacy.py
System Version: v0.6.7

Restores agent_skill_map associations by matching legacy folder paths in
charon/agents_delete/{agent_id}/staging/skills/{folder_name}
against entry_file_path in skill_registry.
"""

import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
LEGACY_AGENTS_DIR = Path("~/Projects/Tools/Charon/charon/agents_delete").expanduser()


def sync_mappings_from_legacy_tree():
    if not STATE_DB_PATH.exists():
        print(f"❌ DB not found: {STATE_DB_PATH}")
        sys.exit(1)

    if not LEGACY_AGENTS_DIR.exists():
        print(f"❌ Legacy directory not found: {LEGACY_AGENTS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # 1. Fetch valid agent IDs
    cursor.execute("SELECT agent_id FROM agent_registry;")
    valid_agents = {row[0] for row in cursor.fetchall()}

    # 2. Fetch active skills from skill_registry with entry_file_path
    cursor.execute("SELECT skill_id, entry_file_path FROM skill_registry WHERE status = 'ACTIVE';")
    active_skills_db = cursor.fetchall()

    # Build folder_name -> list of skill_ids mapping
    folder_to_skill_ids = {}
    for skill_id, entry_file_path in active_skills_db:
        folder_name = Path(entry_file_path).parent.name
        if folder_name not in folder_to_skill_ids:
            folder_to_skill_ids[folder_name] = []
        folder_to_skill_ids[folder_name].append(skill_id)

    print("\n" + "=" * 70)
    print(" 📂 RESTORING AGENT-SKILL MAPPINGS VIA PATH MATCHING")
    print("=" * 70)
    print(f" Legacy Source Directory: {LEGACY_AGENTS_DIR}\n")

    mappings_to_insert = []
    unmatched_folders = []

    # 3. Crawl agents_delete/{agent_id}/staging/skills/{folder_name}
    for agent_dir in LEGACY_AGENTS_DIR.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue

        agent_id = agent_dir.name
        if agent_id not in valid_agents:
            print(f" ⚠️ Skipping unknown agent directory: '{agent_id}'")
            continue

        skills_dir = agent_dir / "staging" / "skills"
        if not skills_dir.exists():
            continue

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue

            folder_name = skill_dir.name

            if folder_name in folder_to_skill_ids:
                for skill_id in folder_to_skill_ids[folder_name]:
                    mappings_to_insert.append((agent_id, skill_id))
            else:
                unmatched_folders.append((agent_id, folder_name))

    # 4. Insert mappings into DB
    inserted_count = 0
    for agent_id, skill_id in mappings_to_insert:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_skill_map (agent_id, skill_id)
            VALUES (?, ?);
        """, (agent_id, skill_id))
        if cursor.rowcount > 0:
            inserted_count += 1

    conn.commit()

    # 5. Final summary
    cursor.execute("SELECT COUNT(*) FROM agent_skill_map;")
    total_mappings = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT skill_id) FROM agent_skill_map;")
    mapped_skills_count = cursor.fetchone()[0]

    print(f" ✅ Restored Mappings     : {inserted_count} new entries inserted")
    print(f" 🔗 Total Active Mappings : {total_mappings}")
    print(f" 🎯 Unique Skills Assigned : {mapped_skills_count} / {len(active_skills_db)}")

    if unmatched_folders:
        print("\n ⚠️ Unmatched Skill Folders (Not active in skill_registry):")
        for a_id, f_id in unmatched_folders:
            print(f"    - Agent '{a_id}' -> Folder '{f_id}'")

    print("=" * 70 + "\n")
    conn.close()


if __name__ == "__main__":
    sync_mappings_from_legacy_tree()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/sync_manifests_to_db.py`

```python
#!/usr/bin/env python3
"""
scripts/sync_manifests_to_db.py
System Version: v0.6.7

Pass 2 Database Repair:
Parses all 38 skill directory manifests, resolves skill_id AND action_name
collisions while keeping handler_name aligned with plugin.py functions,
and safely populates skill_registry in charon_state.db.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Charon.Pass2Repair")


def sync_to_db():
    if not STATE_DB_PATH.exists():
        logger.error(f"Database missing at {STATE_DB_PATH}")
        sys.exit(1)

    if not SKILLS_DIR.exists():
        logger.error(f"Skills directory missing at {SKILLS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    seen_action_names = set()
    rows_to_insert = []
    skill_folders = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]

    for folder in sorted(skill_folders):
        manifest_path = folder / "manifest.json"
        plugin_path = folder / "plugin.py"

        if not manifest_path.exists() or not plugin_path.exists():
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            version = data.get("version", "1.0.0")
            category = data.get("category", "General")
            sys_reqs = json.dumps(data.get("system_requirements", []))
            supported_actions = data.get("supported_actions", {})

            for raw_action_name, action_meta in supported_actions.items():
                handler_name = raw_action_name  # Preserves target python function in plugin.py

                # Resolve action_name and skill_id collisions across distinct plugin folders
                if raw_action_name in seen_action_names:
                    action_name = f"{folder.name}_{raw_action_name}"
                    skill_id = f"sk_{action_name}"
                    logger.warning(
                        f"Collision on action_name '{raw_action_name}' in folder '{folder.name}' "
                        f"-> Renamed action to '{action_name}'"
                    )
                else:
                    action_name = raw_action_name
                    skill_id = f"sk_{action_name}"

                seen_action_names.add(action_name)

                description = action_meta.get("description", "").strip()
                parameters = json.dumps(action_meta.get("parameters", {}))

                rows_to_insert.append((
                    skill_id,
                    action_name,
                    version,
                    category,
                    description,
                    parameters,
                    sys_reqs,
                    "[]",  # consumed_artifacts
                    "[]",  # produced_artifacts
                    str(plugin_path.resolve()),
                    handler_name,
                    "ACTIVE",
                    None,  # quarantine_reason
                    0,  # is_global
                ))

        except Exception as e:
            logger.error(f"Failed parsing {manifest_path}: {e}")

    logger.info(f"Preparing to write {len(rows_to_insert)} verified actions to {STATE_DB_PATH}")

    try:
        conn.execute("BEGIN TRANSACTION;")

        # Purge stale registry items before loading clean ground-truth state
        cursor.execute("DELETE FROM skill_registry;")

        cursor.executemany("""
            INSERT INTO skill_registry (
                skill_id, action_name, version, category, description,
                parameters, system_requirements, consumed_artifacts, produced_artifacts,
                entry_file_path, handler_name, status, quarantine_reason, is_global
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, rows_to_insert)

        conn.commit()

        print("\n" + "=" * 70)
        print(" 🎉 PASS 2 DATABASE REPAIR & SYNC COMPLETE")
        print("=" * 70)
        print(f" Total Folders Processed : {len(skill_folders)}")
        print(f" Actions Indexed into DB : {len(rows_to_insert)}")
        print(" Database Status         : ACTIVE & SYNCHRONIZED")
        print("=" * 70 + "\n")

    except Exception as e:
        conn.rollback()
        logger.error(f"Database repair transaction failed: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    sync_to_db()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/tools_backfill.py`

```python
import json
from pathlib import Path
import sqlite3

db_path = Path.home() / ".local/share/charon/charon_state.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query all mapped skill actions per agent
cursor = conn.execute("SELECT agent_id, action_name FROM agent_skill_map;")
agent_tools = {}

for row in cursor.fetchall():
    aid = row["agent_id"]
    action = row["action_name"]
    if aid not in agent_tools:
        agent_tools[aid] = []

    agent_tools[aid].append({
        "name": action,
        "tool_name": action,
        "enabled": True
    })

# Backfill active_tools in agent_registry
with conn:
    for agent_id, tools in agent_tools.items():
        tools_json = json.dumps(tools)
        conn.execute(
            "UPDATE agent_registry SET active_tools = ?, priority_weight = 1.0 WHERE agent_id = ?;",
            (tools_json, agent_id)
        )

conn.close()
print(f"Successfully backfilled active_tools for {len(agent_tools)} agents.")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/trace_relationships.py`

```python
import shutil
from charon.core.skills.librarian import SkillLibrarian

librarian = SkillLibrarian.get_instance()

# 1. Inspect what Librarian loaded into memory
details = librarian.get_action_details("answer_query")
print("=== Librarian Memory State ===")
print("Action Details:", details)

# 2. Check binary host verification
print("\n=== Host Binary Check ===")
for binary in ["python3", "ollama"]:
    path = shutil.which(binary)
    print(f"Binary '{binary}': {'FOUND at ' + path if path else 'NOT FOUND IN PATH'}")

# 3. Test agent resolution
if hasattr(librarian, "resolve_agent_id_for_role"):
    print("\n=== Role Resolution ===")
    print("system_generalist ->", librarian.resolve_agent_id_for_role("system_generalist"))
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `scripts/verify_db_disk_sync.py`

```python
#!/usr/bin/env python3
"""
scripts/verify_db_disk_sync.py
System Version: v0.6.7

Audit Script:
Verifies that 100% of the skills registered in SQLite exist physically on disk
and checks for any orphaned records or non-existent file paths.
"""

import json
import sqlite3
import sys
from pathlib import Path

STATE_DB_PATH = Path("~/.local/share/charon/charon_state.db").expanduser()
SKILLS_DIR = Path("/charon/storage/dynamic").expanduser()


def audit_db_against_disk():
    if not STATE_DB_PATH.exists():
        print(f"❌ ERROR: Database missing at {STATE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(STATE_DB_PATH))
    cursor = conn.cursor()

    # Get all tables in the DB
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    print("\n" + "=" * 70)
    print(" 🔍 CHARON DATABASE -> DISK SYNC AUDIT")
    print("=" * 70)
    print(f" Database Path : {STATE_DB_PATH}")
    print(f" Tables Found  : {', '.join(tables)}")
    print("=" * 70)

    # 1. Inspect skill_registry table
    cursor.execute("""
        SELECT skill_id, action_name, entry_file_path, status 
        FROM skill_registry;
    """)
    rows = cursor.fetchall()

    missing_paths = []
    missing_manifest_actions = []
    active_count = 0

    for skill_id, action_name, entry_file_path, status in rows:
        if status == "ACTIVE":
            active_count += 1

        path = Path(entry_file_path)

        # Check if plugin.py exists
        if not path.exists():
            missing_paths.append((skill_id, action_name, entry_file_path))
            continue

        # Check if manifest exists in parent folder and contains an action
        manifest_path = path.parent / "manifest.json"
        if not manifest_path.exists():
            missing_manifest_actions.append((skill_id, "Missing manifest.json"))
            continue

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            supported_actions = manifest_data.get("supported_actions", {})

            # Match either exact action_name or handler (for renamed collisions)
            action_found = any(
                act == action_name or f"{path.parent.name}_{act}" == action_name
                for act in supported_actions
            )

            if not action_found:
                missing_manifest_actions.append((skill_id, f"Action '{action_name}' not in {manifest_path}"))
        except Exception as e:
            missing_manifest_actions.append((skill_id, f"Invalid manifest JSON: {e}"))

    # Summary Report
    print(f" Total Rows in DB       : {len(rows)}")
    print(f" Active Actions         : {active_count}")
    print(f" Orphaned Paths (No Py) : {len(missing_paths)}")
    print(f" Manifest Discrepancies : {len(missing_manifest_actions)}")
    print("-" * 70)

    if missing_paths:
        print("\n❌ ORPHANED DB RECORDS (File Missing):")
        for sid, act, pth in missing_paths:
            print(f"  - [{sid}] {act} -> {pth}")

    if missing_manifest_actions:
        print("\n❌ MANIFEST MISMATCHES:")
        for sid, err in missing_manifest_actions:
            print(f"  - [{sid}] {err}")

    if not missing_paths and not missing_manifest_actions:
        print(" SUCCESS: 100% of database records match physical files on disk!")
        print(" ZERO ghost skills detected.")
        print("=" * 70 + "\n")
    else:
        print("\n⚠️ AUDIT FAILED: Discrepancies detected between DB and Disk.")
        print("=" * 70 + "\n")

    conn.close()


if __name__ == "__main__":
    audit_db_against_disk()
```

────────────────────────────────────────────────────────────────────────────────

