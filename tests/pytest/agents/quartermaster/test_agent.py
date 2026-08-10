"""Tests for TheQuartermaster agent orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.agents.quartermaster.agent import TheQuartermaster


@pytest.fixture
def mock_paths(tmp_path: Path):
    db_path = tmp_path / "quartermaster.db"
    datasheet_dir = tmp_path / "datasheets"
    db_path.touch()
    datasheet_dir.mkdir(parents=True, exist_ok=True)
    return db_path, datasheet_dir


class TestTheQuartermasterInit:
    """Tests for initializing TheQuartermaster instance and dependencies."""

    def test_init_custom_paths(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)
        assert qm.db_path == db_path
        assert qm.datasheet_dir == datasheet_dir

    def test_lazy_load_scout_success(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        mock_scout_instance = MagicMock()
        with patch("charon.agents.scout.TheScout", return_value=mock_scout_instance):
            scout = qm._get_scout()
            assert scout == mock_scout_instance

    def test_lazy_load_scout_failure_handled(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        with patch("charon.agents.scout.TheScout", side_effect=ImportError("Scout unavailable")):
            scout = qm._get_scout()
            assert scout is None


class TestTheQuartermasterExecute:
    """Tests for routing and dispatching actions in TheQuartermaster."""

    def test_execute_invalid_action_raises_value_error(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        with pytest.raises(ValueError, match="Unknown action 'invalid_action'"):
            qm.execute("invalid_action", {})

    @pytest.mark.parametrize(
        "action_input,expected_func_path",
        [
            ("check_inventory", "charon.agents.quartermaster.agent.check_inventory"),
            ("inventory", "charon.agents.quartermaster.agent.check_inventory"),
            ("check_stock", "charon.agents.quartermaster.agent.check_inventory"),
            ("fetch_datasheet", "charon.agents.quartermaster.agent.fetch_datasheet"),
            ("get_datasheet", "charon.agents.quartermaster.agent.fetch_datasheet"),
            ("log_inventory", "charon.agents.quartermaster.agent.log_inventory"),
            ("add_inventory", "charon.agents.quartermaster.agent.log_inventory"),
            ("generate_bom", "charon.agents.quartermaster.agent.generate_bom"),
            ("audit_bom", "charon.agents.quartermaster.agent.generate_bom"),
        ],
    )
    def test_action_alias_routing(self, mock_paths, action_input, expected_func_path):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        with patch(expected_func_path, return_value="Success") as mock_handler:
            result = qm.execute(action_input, {"mpn": "NE555"})
            assert result == "Success"
            assert mock_handler.called

    def test_execute_fallback_payload_on_validation_failure(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        with patch(
            "charon.intent.QuartermasterPayload.model_validate",
            side_effect=ValueError("Validation error"),
        ), patch(
            "charon.agents.quartermaster.agent.check_inventory",
            return_value="Fallback Executed",
        ) as mock_handler:
            result = qm.execute(
                action="check_inventory",
                parameters={"part_number": "LM7805"},
                raw_prompt="Check stock for LM7805",
            )
            assert result == "Fallback Executed"
            payload_arg = mock_handler.call_args[0][2]
            assert payload_arg.part_number == "LM7805"

    def test_execute_raw_prompt_populates_query(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        with patch(
            "charon.agents.quartermaster.agent.check_inventory",
            return_value="Check Success",
        ) as mock_check:
            qm.execute(
                action="check_inventory",
                parameters={},
                raw_prompt="What is the stock of STM32?",
            )
            payload_arg = mock_check.call_args[0][2]
            assert payload_arg.query == "What is the stock of STM32?"

    def test_get_scout_returns_cached_instance(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        mock_existing_scout = MagicMock()
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir, scout_agent=mock_existing_scout)

        # Calling _get_scout should return the existing scout without re-importing
        assert qm._get_scout() == mock_existing_scout

    def test_execute_unreachable_action_fallback(self, mock_paths):
        db_path, datasheet_dir = mock_paths
        qm = TheQuartermaster(db_path=db_path, datasheet_dir=datasheet_dir)

        # Force QuartermasterPayload validation to return a payload with an unexpected action
        mock_payload = MagicMock()
        mock_payload.action = "corrupted_action"

        with patch("charon.intent.QuartermasterPayload.model_validate", return_value=mock_payload):
            with pytest.raises(ValueError, match="Unknown action 'check_inventory' for The_Quartermaster"):
                qm.execute("check_inventory", {"part_number": "LM7805"})
