from datetime import datetime
import pytest
from pydantic import ValidationError

from charon.gateway.models import (
    GatekeeperDecision,
    TaskRequest,
    TaskResponse,
    WSEvent,
)


class TestTaskRequest:
    """Tests for TaskRequest model validation and field defaults."""

    def test_task_request_minimal(self) -> None:
        """Verify initialization with required fields and check default values."""
        req = TaskRequest(prompt="Deploy system updates")
        assert req.prompt == "Deploy system updates"
        assert req.client_id == "desktop_concierge"
        assert req.agent_override is None
        assert req.context == {}

    def test_task_request_full(self) -> None:
        """Verify initialization with all custom fields specified."""
        req = TaskRequest(
            prompt="Run full diagnostics",
            client_id="mobile_node",
            agent_override="engineer",
            context={"env": "production", "debug": True},
        )
        assert req.prompt == "Run full diagnostics"
        assert req.client_id == "mobile_node"
        assert req.agent_override == "engineer"
        assert req.context == {"env": "production", "debug": True}

    def test_task_request_missing_required_prompt(self) -> None:
        """Verify validation error when required prompt parameter is missing."""
        with pytest.raises(ValidationError):
            TaskRequest()  # type: ignore[call-arg]


class TestTaskResponse:
    """Tests for TaskResponse model validation and Literal constraints."""

    def test_task_response_minimal(self) -> None:
        """Verify initialization with required fields and default parameters."""
        res = TaskResponse(
            task_id="task-101",
            status="queued",
            message="Task successfully queued.",
        )
        assert res.task_id == "task-101"
        assert res.status == "queued"
        assert res.message == "Task successfully queued."
        assert res.assigned_agent is None
        assert res.result is None

    @pytest.mark.parametrize(
        "valid_status",
        [
            "queued",
            "executing",
            "completed",
            "intercepted",
            "rescinded",
            "cancelled",
            "failed",
        ],
    )
    def test_task_response_valid_statuses(self, valid_status: str) -> None:
        """Verify all valid Literal status values are accepted."""
        res = TaskResponse(
            task_id="task-101",
            status=valid_status,  # type: ignore[arg-type]
            message="Status update",
        )
        assert res.status == valid_status

    def test_task_response_invalid_status(self) -> None:
        """Verify validation error when an invalid status string is provided."""
        with pytest.raises(ValidationError):
            TaskResponse(
                task_id="task-101",
                status="invalid_status",  # type: ignore[arg-type]
                message="Error test",
            )


class TestGatekeeperDecision:
    """Tests for GatekeeperDecision model authorization payload validation."""

    def test_gatekeeper_decision_minimal(self) -> None:
        """Verify initialization with required parameters and defaults."""
        dec = GatekeeperDecision(approval_id="appr-42", decision="proceed")
        assert dec.approval_id == "appr-42"
        assert dec.decision == "proceed"
        assert dec.client_id == "desktop_concierge"
        assert dec.notes is None

    @pytest.mark.parametrize("valid_decision", ["proceed", "rescind", "cancel"])
    def test_gatekeeper_decision_valid_values(self, valid_decision: str) -> None:
        """Verify all valid operator decision options pass validation."""
        dec = GatekeeperDecision(
            approval_id="appr-42",
            decision=valid_decision,  # type: ignore[arg-type]
            notes="Operator approved action.",
        )
        assert dec.decision == valid_decision
        assert dec.notes == "Operator approved action."

    def test_gatekeeper_decision_invalid_value(self) -> None:
        """Verify validation error when an unpermitted decision string is supplied."""
        with pytest.raises(ValidationError):
            GatekeeperDecision(
                approval_id="appr-42",
                decision="reject",  # type: ignore[arg-type]
            )


class TestWSEvent:
    """Tests for WSEvent model validation and automatic timestamp generation."""

    def test_ws_event_minimal(self) -> None:
        """Verify default creation generates valid ISO 8601 UTC timestamp and default fields."""
        event = WSEvent(event_type="status_change")
        assert event.event_type == "status_change"
        assert event.task_id is None
        assert event.client_id is None
        assert event.data == {}

        # Validate timestamp format compliance
        parsed_dt = datetime.fromisoformat(event.timestamp)
        assert parsed_dt.tzinfo is not None

    @pytest.mark.parametrize(
        "valid_event_type",
        [
            "status_change",
            "agent_log",
            "gatekeeper_intercept",
            "concierge_suggestion",
            "task_complete",
            "overseer_report",
            "steward_event",
            "system_alert",
            "error",
        ],
    )
    def test_ws_event_valid_event_types(self, valid_event_type: str) -> None:
        """Verify all valid event discriminator types pass validation."""
        event = WSEvent(
            event_type=valid_event_type,  # type: ignore[arg-type]
            task_id="task-999",
            data={"details": "payload"},
        )
        assert event.event_type == valid_event_type
        assert event.task_id == "task-999"
        assert event.data == {"details": "payload"}

    def test_ws_event_invalid_event_type(self) -> None:
        """Verify validation error when an unknown event type is provided."""
        with pytest.raises(ValidationError):
            WSEvent(event_type="unknown_event")  # type: ignore[arg-type]
