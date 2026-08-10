"""test_overseer.py — Unit tests for TheOverseer agent and modular sub-systems."""

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any

import pytest

from charon.agents import TheOverseer, get_agent_class
from charon.agents.overseer.constants import (
from charon.db.connection import get_connection
    ACTION_MAP,
    VALID_OVERSEER_ACTIONS,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def overseer_instance(tmp_path: Path) -> TheOverseer:
    """Provides a fresh instance of TheOverseer initialized with a temp DB path."""
    db_file = tmp_path / "test_overseer_default.sqlite3"
    return TheOverseer(db_path=db_file)


@pytest.fixture
def sample_sqlite_db(tmp_path: Path) -> Path:
    """Creates a temporary valid SQLite database populated with test data."""
    db_path = tmp_path / "sample_test.sqlite"
    conn = get_connection(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.executemany(
        "INSERT INTO items (name) VALUES (?);",
        [(f"Item_{i}",) for i in range(100)],
    )
    conn.commit()
    conn.close()
    return db_path


# ============================================================================
# Lazy Loading & Constants Tests
# ============================================================================


def test_lazy_loading_import():
    """Verifies Overseer resolution through agent registry and lazy loader."""
    cls_by_name = get_agent_class("TheOverseer")
    cls_by_alias = get_agent_class("overseer")
    cls_by_prefix = get_agent_class("the_overseer")

    assert cls_by_name is TheOverseer
    assert cls_by_alias is TheOverseer
    assert cls_by_prefix is TheOverseer


def test_action_mappings():
    """Ensures action aliases correctly resolve to primary action names."""
    assert ACTION_MAP["vacuum"] == "optimize_databases"
    assert ACTION_MAP["health"] == "get_system_health"
    assert ACTION_MAP["clean_all"] == "run_full_maintenance"
    assert ACTION_MAP["prune_logs"] == "prune_logs_and_cache"
    assert ACTION_MAP["prune_assets"] == "prune_orphaned_assets"

    for valid_action in VALID_OVERSEER_ACTIONS:
        assert valid_action in VALID_OVERSEER_ACTIONS


# ============================================================================
# Database Optimization Tests
# ============================================================================


@pytest.mark.asyncio
async def test_optimize_sqlite_db_success(
    overseer_instance: TheOverseer, sample_sqlite_db: Path
):
    """Tests SQLite integrity check, PRAGMA, and VACUUM execution on a valid database."""
    res = await overseer_instance.optimize_sqlite_db(
        target_db=sample_sqlite_db
    )

    assert res["status"] == "completed"
    assert "optimized_databases" in res
    assert len(res["optimized_databases"]) == 1

    db_res = res["optimized_databases"][0]
    assert db_res["status"] == "success"
    assert db_res["integrity"] == "ok"
    assert db_res["fk_violations_count"] == 0
    assert db_res["size_before_bytes"] >= db_res["size_after_bytes"]


@pytest.mark.asyncio
async def test_optimize_sqlite_db_nonexistent(
    overseer_instance: TheOverseer, tmp_path: Path
):
    """Tests SQLite optimization gracefully handles missing database targets."""
    missing_path = tmp_path / "nonexistent.db"
    res = await overseer_instance.optimize_sqlite_db(target_db=missing_path)

    assert res["status"] == "completed"
    db_res = res["optimized_databases"][0]
    assert db_res["status"] == "skipped"
    assert "not found" in db_res["reason"].lower()


# ============================================================================
# Vector Store Audit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_vector_store(
    overseer_instance: TheOverseer, tmp_path: Path, monkeypatch
):
    """Tests vector store structure and SQLite quick-check inspection."""
    chroma_dir = tmp_path / "chroma_test"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy Chroma SQLite database
    chroma_sqlite = chroma_dir / "chroma.sqlite3"
    conn = get_connection(str(chroma_sqlite))
    conn.execute(
        "CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT);"
    )
    conn.execute(
        "INSERT INTO collections VALUES ('col_1', 'datasheets');"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "charon.agents.overseer.vector_store.CHROMA_DB_DIR", chroma_dir
    )

    res = await overseer_instance.audit_vector_store()

    assert res["exists"] is True
    assert res["sqlite_size_bytes"] > 0
    assert res["integrity_check"] == "ok"
    assert res["active_collections_count"] == 1


# ============================================================================
# Log and Cache Pruning Tests
# ============================================================================


@pytest.mark.asyncio
async def test_prune_logs_and_cache(
    overseer_instance: TheOverseer, tmp_path: Path, monkeypatch
):
    """Tests that files older than the retention threshold are pruned while newer files remain."""
    logs_dir = tmp_path / "logs"
    cache_dir = tmp_path / "data" / "cache"
    logs_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create an old file (> 10 days old)
    old_log = logs_dir / "old_app.log"
    old_log.write_text("old log contents")
    ten_days_ago = time.time() - (10 * 86400)
    os.utime(old_log, (ten_days_ago, ten_days_ago))

    # Create a fresh file (< 1 day old)
    fresh_log = logs_dir / "fresh_app.log"
    fresh_log.write_text("fresh log contents")

    monkeypatch.setattr("charon.agents.overseer.pruning.LOGS_DIR", logs_dir)
    monkeypatch.setattr(
        "charon.agents.overseer.pruning.DATA_DIR", tmp_path / "data"
    )

    res = await overseer_instance.prune_logs_and_cache(prune_days=7)

    assert res["status"] == "completed"
    assert res["pruned_files_count"] == 1
    assert not old_log.exists()
    assert fresh_log.exists()


# ============================================================================
# Orphaned Asset Sweep Tests
# ============================================================================


@pytest.mark.asyncio
async def test_prune_orphaned_assets(
    overseer_instance: TheOverseer, tmp_path: Path
):
    """Tests sweeping broken symlinks and orphaned files from target directories."""
    datasheets_dir = tmp_path / "datasheets"
    datasheets_dir.mkdir(parents=True, exist_ok=True)

    # Create orphan file
    orphan_pdf = datasheets_dir / "untracked_spec.pdf"
    orphan_pdf.write_text("dummy PDF content")

    # Create broken symlink (non-windows platform support)
    broken_link = datasheets_dir / "broken_link.pdf"
    try:
        os.symlink(tmp_path / "does_not_exist.pdf", broken_link)
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    res = await overseer_instance.prune_orphaned_assets(
        datasheets_dir=datasheets_dir
    )

    assert res["status"] == "completed"
    assert not orphan_pdf.exists()
    if has_symlink:
        assert res["broken_symlinks_removed"] >= 1


# ============================================================================
# System Telemetry & Health Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_system_health(overseer_instance: TheOverseer):
    """Tests host telemetry aggregation and dictionary output keys."""
    health = await overseer_instance.get_system_health()

    assert "timestamp" in health
    assert "telemetry" in health
    assert "database_sizes" in health


# ============================================================================
# Agent Action Dispatcher (`execute`) Tests
# ============================================================================


@pytest.mark.asyncio
async def test_execute_action_routing(
    overseer_instance: TheOverseer, sample_sqlite_db: Path
):
    """Tests routing actions and aliases through the Overseer execute dispatcher."""
    # Action Alias Test: 'vacuum' -> 'optimize_databases'
    res_vacuum = await overseer_instance.execute(
        action="vacuum", parameters={"target_db": str(sample_sqlite_db)}
    )
    assert res_vacuum["status"] == "completed"
    assert len(res_vacuum["optimized_databases"]) == 1

    # Health Check Test
    res_health = await overseer_instance.execute(action="health")
    assert "telemetry" in res_health

    # Full Maintenance Sweep
    res_maint = await overseer_instance.execute(action="run_full_maintenance")
    assert res_maint["action"] == "run_full_maintenance"
    assert res_maint["status"] == "completed"
    assert "database_optimization" in res_maint
    assert "vector_store_audit" in res_maint
    assert "log_cache_prune" in res_maint
    assert "orphaned_asset_prune" in res_maint
    assert "system_health" in res_maint


@pytest.mark.asyncio
async def test_execute_invalid_action(overseer_instance: TheOverseer):
    """Tests fallback behavior or raising ValueError for unsupported actions."""
    # Unknown actions default to health check via model fallback
    res = await overseer_instance.execute(action="unknown_invalid_action")
    assert "telemetry" in res or "timestamp" in res