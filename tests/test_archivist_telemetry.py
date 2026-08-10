import tempfile
import pytest
from pathlib import Path
from typing import Dict, Any, List

from charon.agents.archivist.agent import TheArchivist


@pytest.fixture
def temp_chroma_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_archivist_telemetry_stream(temp_chroma_db):
    captured_events: List[Dict[str, Any]] = []

    # 1. Correct single-argument dictionary callback
    def telemetry_callback(event: Dict[str, Any]):
        captured_events.append(event)

    # 2. Instantiate agent and bind telemetry callback
    archivist = TheArchivist(db_path=temp_chroma_db)
    archivist.bind_telemetry(telemetry_callback)

    # 3. Execute store_record action
    store_result = archivist.execute(
        action="store_record",
        parameters={
            "query": "Always use proper ESD grounding when handling microcontrollers.",
            "rule_category": "safety",
        },
        raw_prompt="Record safety rule about ESD grounding",
    )

    assert store_result is not None
    assert len(captured_events) >= 1

    # Verify canonical event types matching base.py
    event_types = [e["type"] for e in captured_events]
    assert "agent_action" in event_types or "task_progress" in event_types or "telemetry_trace" in event_types

    for event in captured_events:
        assert event["agent_name"] == archivist.name

    # Verify action event structure under the "data" sub-key
    action_events = [e for e in captured_events if e["type"] == "agent_action"]
    if action_events:
        assert action_events[0]["data"]["action"] == "store_record"


def test_archivist_search_telemetry(temp_chroma_db):
    captured_events: List[Dict[str, Any]] = []

    def telemetry_callback(event: Dict[str, Any]):
        captured_events.append(event)

    archivist = TheArchivist(db_path=temp_chroma_db)
    archivist.bind_telemetry(telemetry_callback)

    # Search query
    archivist.execute(
        action="search_ledger",
        parameters={"query": "ESD safety guidelines"},
        raw_prompt="How should ESD be handled?",
    )

    # Verify telemetry trace events
    trace_events = [e for e in captured_events if e["type"] == "telemetry_trace"]
    assert len(trace_events) > 0
    assert any("event_type" in t["data"] for t in trace_events)