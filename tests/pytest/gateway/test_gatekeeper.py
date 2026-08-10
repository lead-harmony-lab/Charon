from typing import Optional
import pytest
from pydantic import BaseModel

from charon.gateway.gatekeeper import GatekeeperManager
from charon.intent import AgentEnum


class SamplePayload(BaseModel):
    action: str = "execute_script"
    requires_approval: bool = True
    memory_candidate: bool = True
    confirmed: bool = False
    short_param: str = "safe_value"
    long_param: str = (
        "This is a long param string exceeding 80 characters limit to trigger block formatting in manifest message output."
    )
    empty_param: Optional[str] = None


class MinimalPayload(BaseModel):
    requires_approval: bool = False


@pytest.fixture
def gatekeeper() -> GatekeeperManager:
    """Fixture providing a clean GatekeeperManager instance."""
    return GatekeeperManager()


class TestGatekeeperManager:
    """Tests for GatekeeperManager pre-flight authorization state handling."""

    def test_init(self, gatekeeper: GatekeeperManager) -> None:
        """Verify default initial state of GatekeeperManager."""
        assert gatekeeper.awaiting_approval is False
        assert gatekeeper.pending_agent is None
        assert gatekeeper.pending_extraction is None
        assert gatekeeper.pending_raw_input == ""

    def test_requires_approval_true(self, gatekeeper: GatekeeperManager) -> None:
        """Verify requires_approval returns True when model flag is set."""
        payload = SamplePayload(requires_approval=True)
        assert gatekeeper.requires_approval(payload) is True

    def test_requires_approval_false(self, gatekeeper: GatekeeperManager) -> None:
        """Verify requires_approval returns False when model flag is False or missing."""
        payload = MinimalPayload(requires_approval=False)
        assert gatekeeper.requires_approval(payload) is False

    def test_requires_approval_none(self, gatekeeper: GatekeeperManager) -> None:
        """Verify requires_approval handles None gracefully."""
        assert gatekeeper.requires_approval(None) is False

    def test_intercept_task_sets_state_and_formats_manifest(
        self, gatekeeper: GatekeeperManager
    ) -> None:
        """Verify intercept_task stores pending state and returns formatted manifest."""
        payload = SamplePayload()
        raw_input = "Run the script with high permissions"

        manifest, action = gatekeeper.intercept_task(
            AgentEnum.ENGINEER, payload, raw_input
        )

        # State updates
        assert gatekeeper.awaiting_approval is True
        assert gatekeeper.pending_agent == AgentEnum.ENGINEER
        assert gatekeeper.pending_extraction == payload
        assert gatekeeper.pending_raw_input == raw_input

        # Output formatting
        assert action == "execute_script"
        assert f"Target Agent : {AgentEnum.ENGINEER.value}" in manifest
        assert "Action        : execute_script" in manifest  # <--- Change from 9 spaces to 8
        assert "• short_param: safe_value" in manifest
        assert "'''\n    This is a long param string" in manifest

        # Exclusions check
        assert "requires_approval" not in manifest
        assert "memory_candidate" not in manifest
        assert "empty_param" not in manifest

    def test_intercept_task_no_parameters(
        self, gatekeeper: GatekeeperManager
    ) -> None:
        """Verify intercept_task handles payloads with no reportable parameters."""
        payload = MinimalPayload()

        manifest, action = gatekeeper.intercept_task(
            AgentEnum.ARCHITECT, payload, "Create architectural plan"
        )

        assert action == "unknown"
        assert "• No parameters specified." in manifest

    def test_handle_approval_with_proceed_in_input(
        self, gatekeeper: GatekeeperManager
    ) -> None:
        """Verify handle_approval sets confirmed attribute, retains user input, and resets state."""
        payload = SamplePayload()
        gatekeeper.intercept_task(AgentEnum.ENGINEER, payload, "User requested proceed")

        agent, extraction, eff_input = gatekeeper.handle_approval()

        assert agent == AgentEnum.ENGINEER
        assert extraction == payload
        assert getattr(extraction, "confirmed") is True
        assert eff_input == "User requested proceed"

        # Verify state reset
        assert gatekeeper.awaiting_approval is False
        assert gatekeeper.pending_agent is None
        assert gatekeeper.pending_extraction is None
        assert gatekeeper.pending_raw_input == ""

    def test_handle_approval_appends_proceed_if_missing(
        self, gatekeeper: GatekeeperManager
    ) -> None:
        """Verify handle_approval appends 'proceed' when not explicitly present in raw_input."""
        payload = SamplePayload()
        gatekeeper.intercept_task(AgentEnum.ENGINEER, payload, "Do it now")

        _, _, eff_input = gatekeeper.handle_approval()

        assert eff_input == "Do it now proceed"

    def test_handle_approval_without_confirmed_attribute(
        self, gatekeeper: GatekeeperManager
    ) -> None:
        """Verify handle_approval handles payloads lacking a 'confirmed' attribute without error."""
        payload = MinimalPayload()
        gatekeeper.intercept_task(AgentEnum.ENGINEER, payload, "Execute action")

        agent, extraction, eff_input = gatekeeper.handle_approval()

        assert agent == AgentEnum.ENGINEER
        assert extraction == payload
        assert not hasattr(extraction, "confirmed")
        assert eff_input == "Execute action proceed"

    def test_reset(self, gatekeeper: GatekeeperManager) -> None:
        """Verify reset clears all internal pending authorization state."""
        payload = SamplePayload()
        gatekeeper.intercept_task(AgentEnum.ENGINEER, payload, "Pending task")

        gatekeeper.reset()

        assert gatekeeper.awaiting_approval is False
        assert gatekeeper.pending_agent is None
        assert gatekeeper.pending_extraction is None
        assert gatekeeper.pending_raw_input == ""
