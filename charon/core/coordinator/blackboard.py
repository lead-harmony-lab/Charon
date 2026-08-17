"""
charon/core/coordinator/blackboard.py
System Version: v1.0.0 | File Revision: 10.0.0

Module: DB-backed state blackboard and execution TaskBlackboard wrapper.
Refactored for the Zero-Trust Execution Engine paradigm.
Provides strongly-typed schemas for artifact propagation, task payloads,
and strict diagnostic gap tracing, persisting instantly to SQLite state.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from charon.core.contracts import ContractResponse, ExecutionStatus


class TaskStatus(str, Enum):
    """Lifecycle status of a Task in the Zero-Trust Coordinator."""
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ThoughtType(str, Enum):
    """Categorizes the phase of internal role/coordinator reasoning."""
    ANALYSIS = "ANALYSIS"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    REFLECTION = "REFLECTION"
    ERROR = "ERROR"


class ThoughtRecord(BaseModel):
    """Granular CoT reasoning step emitted by the Coordinator or Agents."""
    model_config = ConfigDict(strict=True, extra="forbid")

    record_id: str = Field(default_factory=lambda: f"thg-{uuid.uuid4().hex[:6]}")
    source_role: str = Field(description="Abstract role or agent_id emitting the thought.")
    thought_type: ThoughtType = Field(default=ThoughtType.ANALYSIS)
    message: str = Field(description="Internal CoT narrative payload.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExecutionStepRecord(BaseModel):
    """Audit log entry representing a single Work Contract execution turn."""
    model_config = ConfigDict(strict=True, extra="forbid")

    step_number: int = Field(description="Index of the step execution order.")
    agent_id: str = Field(description="The agent_id that executed the envelope.")
    skill_id: str = Field(description="The authorized tool used.")
    status: str = Field(default="SUCCESS", description="Outcome status of the Work Contract.")
    output_summary: str = Field(default="", description="Summary of the Artifact produced.")
    diagnostic_context: Optional[Dict[str, Any]] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TaskBlackboard:
    """
    Lightweight, DB-backed wrapper for task state.
    Provides agents and the Coordinator a clean interface to mutate state
    without holding massive JSON structures in memory.
    """

    def __init__(self, db_path: Union[str, Path], task_id: str):
        self.db_path = Path(db_path)
        self.task_id = task_id

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_results_payload(self) -> Dict[str, Any]:
        """Fetches and parses the current results_json from DB."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT results_json FROM task_state WHERE task_id = ?",
                (self.task_id,)
            ).fetchone()

            if not row or not row["results_json"]:
                return {"artifacts": {}, "history": [], "thought_stream": []}
            return json.loads(row["results_json"])

    def _update_results_payload(self, payload: Dict[str, Any]) -> None:
        """Serializes and writes the results payload back to DB."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE task_state SET results_json = ?, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
                (json.dumps(payload), self.task_id)
            )

    # ---------------------------------------------------------
    # CORE STATE MUTATORS
    # ---------------------------------------------------------

    def set_artifact(self, key: str, value: Any) -> None:
        """Stores a ground truth artifact directly to disk."""
        payload = self._get_results_payload()
        if "artifacts" not in payload:
            payload["artifacts"] = {}
        payload["artifacts"][key] = value
        self._update_results_payload(payload)

    def get_artifact(self, key: str, default: Any = None) -> Any:
        """Retrieves a ground truth artifact from disk."""
        payload = self._get_results_payload()
        return payload.get("artifacts", {}).get(key, default)

    def emit_thought(self, source_role: str, message: str, thought_type: ThoughtType = ThoughtType.ANALYSIS) -> ThoughtRecord:
        """Emits a live CoT reasoning event directly to the DB."""
        record = ThoughtRecord(
            source_role=source_role,
            thought_type=thought_type,
            message=message
        )
        payload = self._get_results_payload()
        if "thought_stream" not in payload:
            payload["thought_stream"] = []

        payload["thought_stream"].append(record.model_dump())
        self._update_results_payload(payload)
        return record

    def record_step(self, agent_id: str, skill_id: str, status: str = "SUCCESS", output_summary: str = "", diagnostic_context: Optional[Dict[str, Any]] = None) -> None:
        """Appends an execution turn to history in the DB."""
        payload = self._get_results_payload()
        if "history" not in payload:
            payload["history"] = []

        step_number = len(payload["history"]) + 1
        record = ExecutionStepRecord(
            step_number=step_number,
            agent_id=agent_id,
            skill_id=skill_id,
            status=status,
            output_summary=output_summary,
            diagnostic_context=diagnostic_context
        )

        payload["history"].append(record.model_dump())
        self._update_results_payload(payload)

    # ---------------------------------------------------------
    # COORDINATOR PLAN SYNC
    # ---------------------------------------------------------

    def get_plan(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT plan_json FROM task_state WHERE task_id = ?", (self.task_id,)).fetchone()
            if row and row["plan_json"]:
                return json.loads(row["plan_json"])
            return None

    def get_current_step_index(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT current_step_index FROM task_state WHERE task_id = ?", (self.task_id,)).fetchone()
            return row["current_step_index"] if row else 0

    def get_status(self) -> TaskStatus:
        with self._get_connection() as conn:
            row = conn.execute("SELECT status FROM task_state WHERE task_id = ?", (self.task_id,)).fetchone()
            return TaskStatus(row["status"]) if row else TaskStatus.PENDING