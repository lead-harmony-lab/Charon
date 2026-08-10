"""
charon/sdk/models.py
System Version: v0.1.0 | File Revision: 2.0.0

Data models, event typing, and serialization helpers for Charon SDK.
"""

from datetime import datetime, timezone
import os
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

# Graceful fallback for configurations when SDK is executed on standalone peripheral nodes
try:
    from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
except ImportError:
    if "CHARON_API_KEY" not in os.environ:
        env_path = os.path.expanduser("~/.config/charon/env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ[k.strip()] = v.strip().strip("'\"")
            except Exception:
                pass

    API_KEY_HEADER_NAME = os.getenv("CHARON_API_KEY_HEADER", "X-API-Key")
    CHARON_API_KEY = os.getenv("CHARON_API_KEY", "charon-secret-key-change-me")

# Graceful fallback for models when SDK is executed on standalone peripheral nodes
try:
    from charon.gateway.models import GatekeeperDecision, TaskRequest, TaskResponse, WSEvent
except ImportError:
    from pydantic import BaseModel, Field

    class WSEvent(BaseModel):
        event_type: str
        task_id: Optional[str] = None
        client_id: Optional[str] = None
        data: Dict[str, Any] = Field(default_factory=dict)
        timestamp: str = Field(
            default_factory=lambda: datetime.now(timezone.utc).isoformat()
        )

    class TaskRequest(BaseModel):
        prompt: str
        client_id: str
        agent_override: Optional[str] = None
        context: Dict[str, Any] = Field(default_factory=dict)

    class TaskResponse(BaseModel):
        task_id: str
        status: str
        assigned_agent: Optional[str] = None
        message: Optional[str] = None

    class GatekeeperDecision(BaseModel):
        approval_id: str
        decision: Literal["proceed", "rescind", "cancel"]
        client_id: str
        notes: Optional[str] = None

# Type alias for event callbacks
EventHandler = Callable[[WSEvent], Awaitable[None]]


def dump_model(model_obj: Any) -> Dict[str, Any]:
    """Serializes a Pydantic model across v1 and v2 releases."""
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()
    elif hasattr(model_obj, "dict"):
        return model_obj.dict()
    elif isinstance(model_obj, dict):
        return model_obj
    return dict(model_obj)