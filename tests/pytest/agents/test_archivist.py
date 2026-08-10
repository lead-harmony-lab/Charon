"""Unit tests for TheArchivist specialist agent (ledger management and datasheet RAG store)."""

from pathlib import Path
from unittest.mock import patch
import pytest
from pydantic import ValidationError

from charon.agents.archivist import (
    TheArchivist,
    _chunk_text,
    _get_payload_val,
    ensure_ecosystem_directories,
)


@pytest.fixture
def archivist_agent(tmp_path: Path) -> TheArchivist:
    """Fixture providing an instance of TheArchivist with an isolated ChromaDB directory."""
    db_dir = tmp_path / "chroma_db"
    return TheArchivist(db_path=db_dir)


@pytest.fixture
def dummy_pdf_file(tmp_path: Path) -> Path:
    """Creates a dummy PDF file path for testing datasheet indexing."""
    pdf_path = tmp_path / "STM32F407.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 Mock PDF Content for STM32 Microcontroller")
    return pdf_path


# =============================================================================
# 1. INITIALIZATION & RE-EXPORTS
# =============================================================================


def test_archivist_initialization(tmp_path: Path):
    """Tests that TheArchivist initializes collections in the specified custom directory."""
    db_dir = tmp_path / "custom_chroma"
    agent = TheArchivist(db_path=db_dir)

    assert agent.db_path == db_dir.resolve()
    assert agent.collection.name == "ledger"
    assert agent.datasheet_collection.name == "datasheet_knowledge"


def test_package_reexports():
    """Validates top-level package imports from charon.agents.archivist."""
    assert TheArchivist is not None
    assert callable(_chunk_text)
    assert callable(_get_payload_val)
    assert callable(ensure_ecosystem_directories)


# =============================================================================
# 2. SYSTEM LEDGER OPERATIONS (STORE, SEARCH, DEDUPLICATION)
# =============================================================================


def test_store_record_and_deduplication(archivist_agent: TheArchivist):
    """Tests storing facts into the ledger and rejecting exact duplicates."""
    fact = "Always use M3 304 stainless steel screws for outdoor enclosures."

    # First insertion
    res1 = archivist_agent.execute(
        action="store_record",
        parameters={"fact": fact, "category": "hardware_standards"},
    )
    assert "securely committed to the ledger" in res1
    assert "hardware_standards" in res1

    # Duplicate insertion attempt
    res2 = archivist_agent.execute(
        action="store_record",
        parameters={"fact": fact, "category": "hardware_standards"},
    )
    assert "already present in the ledger" in res2


def test_store_record_missing_fact(archivist_agent: TheArchivist):
    """Tests storing a record without providing a fact string."""
    res = archivist_agent.execute(
        action="store_record",
        parameters={"category": "hardware_standards"},
    )
    assert "No explicit fact or rule provided" in res


def test_search_ledger(archivist_agent: TheArchivist):
    """Tests rule retrieval from the ledger."""
    # Search empty ledger
    res_empty = archivist_agent.execute(
        action="search_ledger", parameters={"query": "stainless screws"}
    )
    assert "The ledger is currently empty" in res_empty

    # Store a rule and query for it
    fact = "Use anodized aluminum 6061-T6 for heat sinks in thermal design."
    archivist_agent.execute(
        action="record_rule", parameters={"fact": fact, "category": "thermal"}
    )

    res_found = archivist_agent.execute(
        action="search_ledger", parameters={"query": "heat sinks aluminum"}
    )
    assert "anodized aluminum 6061-T6" in res_found


def test_search_ledger_empty_query(archivist_agent: TheArchivist):
    """Tests searching the ledger with an empty query."""
    res = archivist_agent.execute(action="search_ledger", parameters={})
    assert "No search query provided" in res


# =============================================================================
# 3. EXPUNGING RECORDS
# =============================================================================


def test_expunge_record_substring_match(archivist_agent: TheArchivist):
    """Tests deleting ledger rules via substring matching and public delete helper."""
    rule1 = "Obsolete Protocol v1.0 should never be used."
    rule2 = "Legacy Driver v2.1 requires legacy kernel."

    archivist_agent.execute(action="record_rule", parameters={"fact": rule1})
    archivist_agent.execute(action="record_rule", parameters={"fact": rule2})

    # Expunge via action
    res_expunge = archivist_agent.execute(
        action="expunge_record", parameters={"target_concept": "Obsolete Protocol"}
    )
    assert "Struck 1 record(s) matching 'Obsolete Protocol'" in res_expunge

    # Expunge via public helper method
    res_helper = archivist_agent.delete_ledger_rule("Legacy Driver")
    assert "Struck 1 record(s) matching 'Legacy Driver'" in res_helper


def test_expunge_record_empty_or_missing_target(archivist_agent: TheArchivist):
    """Tests expunging without specifying a target or on an empty ledger."""
    res_empty = archivist_agent.execute(
        action="expunge_record", parameters={"target_concept": "nonexistent"}
    )
    assert "ledger is currently empty" in res_empty

    archivist_agent.execute(
        action="record_rule", parameters={"fact": "Some valid system rule"}
    )
    res_no_param = archivist_agent.execute(action="expunge_record", parameters={})
    assert "Please specify the concept" in res_no_param


# =============================================================================
# 4. SUMMARIZE LEDGER
# =============================================================================


def test_summarize_ledger(archivist_agent: TheArchivist):
    """Tests categorized ledger summarization."""
    assert "currently empty" in archivist_agent.execute(
        action="summarize_ledger", parameters={}
    )

    archivist_agent.execute(
        action="store_record",
        parameters={
            "fact": "Always wear eye protection in active workspaces.",
            "category": "safety_rules",
        },
    )
    archivist_agent.execute(
        action="store_record",
        parameters={
            "fact": "Keep emergency exit pathways clear of all obstructions.",
            "category": "safety_rules",
        },
    )
    archivist_agent.execute(
        action="store_record",
        parameters={
            "fact": "Torque all M6 chassis bolts to 10 Nm.",
            "category": "mechanical_specs",
        },
    )

    summary = archivist_agent.execute(
        action="summarize_ledger", parameters={}
    )
    assert "System Memory" in summary
    assert "3 records" in summary
    assert "Safety Rules" in summary
    assert "Mechanical Specs" in summary


# =============================================================================
# 5. DATASHEET INDEXING & RAG SEARCH
# =============================================================================


@patch("charon.agents.archivist.datasheets.extract_text_from_pdf")
def test_index_datasheet_and_search(
    mock_extract_pdf, archivist_agent: TheArchivist, dummy_pdf_file: Path
):
    """Tests PDF datasheet chunk indexing and semantic search over datasheets."""
    mock_extract_pdf.return_value = [
        (1, "STM32F407 High-performance ARM Cortex-M4 MCU with DSP and FPU."),
        (2, "Operating voltage: 1.8V to 3.6V. Operating temperature: -40 to 85°C."),
    ]

    # Index datasheet action
    res_index = archivist_agent.execute(
        action="index_datasheet",
        parameters={
            "file_path": str(dummy_pdf_file),
            "mpn": "STM32F407VG",
            "category": "Microcontrollers",
        },
    )
    assert "Successfully indexed" in res_index
    assert "STM32F407VG" in res_index

    # Search datasheet action
    res_search = archivist_agent.execute(
        action="search_datasheets",
        parameters={
            "query": "What is the operating voltage range?",
            "mpn": "STM32F407VG",
        },
    )
    assert "Retrieved" in res_search
    assert "1.8V to 3.6V" in res_search
    assert "MPN: STM32F407VG" in res_search


def test_index_datasheet_missing_parameters(archivist_agent: TheArchivist):
    """Tests error handling when required indexing parameters are missing."""
    res = archivist_agent.execute(
        action="index_pdf", parameters={"file_path": "/tmp/test.pdf"}
    )
    assert "Both 'file_path' and 'mpn' parameters are required" in res


def test_search_datasheets_empty_store(archivist_agent: TheArchivist):
    """Tests searching an unpopulated datasheet vector store."""
    res = archivist_agent.execute(
        action="search_datasheets", parameters={"query": "voltage range"}
    )
    assert "datasheet vector store is currently empty" in res


# =============================================================================
# 6. LEDGER TO DATASHEET FALLBACK ROUTING
# =============================================================================


@patch("charon.agents.archivist.datasheets.extract_text_from_pdf")
def test_search_ledger_fallback_to_datasheet(
    mock_extract_pdf, archivist_agent: TheArchivist, dummy_pdf_file: Path
):
    """Tests fallback from ledger search to datasheet search when ledger has no results."""
    mock_extract_pdf.return_value = [
        (1, "TXS0108E 8-bit bidirectional voltage-level translator for open-drain applications.")
    ]

    # Index a datasheet into datasheet collection, keep system ledger empty
    archivist_agent.index_pdf_datasheet(
        pdf_path=dummy_pdf_file, mpn="TXS0108E", metadata={"category": "Logic"}
    )

    # Search system ledger (empty) -> should automatically bridge to datasheet store
    res_fallback = archivist_agent.execute(
        action="search_ledger",
        parameters={"query": "voltage level translator"},
    )
    assert "Retrieved" in res_fallback
    assert "TXS0108E" in res_fallback


# =============================================================================
# 7. ROUTING & UNKNOWN ACTIONS
# =============================================================================


def test_invalid_action_raises_exception(archivist_agent: TheArchivist):
    """Tests that an unsupported action raises a ValidationError during payload validation."""
    with pytest.raises((ValueError, ValidationError)):
        archivist_agent.execute(
            action="invalid_action", parameters={"query": "test"}
        )
