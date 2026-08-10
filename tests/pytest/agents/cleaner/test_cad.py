"""Tests for The Cleaner CAD iteration sweeping and archiving handlers."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.agents.cleaner.cad import CADManager
from charon.intent import CleanerPayload


class TestCADManager:
    """Test suite covering CAD iteration detection, grouping, and archiving."""

    def test_init_default_and_custom_projects_dir(self, tmp_path: Path):
        """Tests CADManager initialization with default and custom projects directories."""
        manager_custom = CADManager(projects_dir=tmp_path)
        assert manager_custom.projects_dir == tmp_path.resolve()

        manager_default = CADManager()
        assert isinstance(manager_default.projects_dir, Path)

    def test_sweep_cad_iterations_missing_parameters(self):
        """Tests that missing project_name and base_path returns an error message."""
        manager = CADManager()
        result = manager.sweep_cad_iterations(payload=None, params={})
        assert "Error: A 'project_name' or 'base_path' parameter is required" in result

    def test_sweep_cad_iterations_base_path_with_project_subdir(self, tmp_path: Path):
        """Tests resolution when base_path is provided and project_name exists as a subdirectory."""
        base_dir = tmp_path / "workspaces"
        proj_dir = base_dir / "drone_mount"
        cad_dir = proj_dir / "cad"
        cad_dir.mkdir(parents=True, exist_ok=True)

        manager = CADManager()
        result = manager.sweep_cad_iterations(
            params={"base_path": str(base_dir), "project_name": "drone_mount"}
        )
        assert f"No versioned CAD iterations (e.g. *_v1.step) found in {cad_dir}" in result

    def test_sweep_cad_iterations_project_name_only(self, tmp_path: Path):
        """Tests resolution using project_name relative to projects_dir."""
        proj_dir = tmp_path / "robot_arm"
        proj_dir.mkdir(parents=True, exist_ok=True)

        manager = CADManager(projects_dir=tmp_path)
        payload = CleanerPayload(action="sweep_cad_iterations", project_name="robot_arm")
        result = manager.sweep_cad_iterations(payload=payload)
        assert f"No versioned CAD iterations (e.g. *_v1.step) found in {proj_dir}" in result

    def test_sweep_cad_iterations_nonexistent_directory(self, tmp_path: Path):
        """Tests error returned when target CAD directory does not exist."""
        manager = CADManager(projects_dir=tmp_path)
        result = manager.sweep_cad_iterations(params={"project_name": "missing_proj"})
        assert "CAD directory not found at" in result

    def test_sweep_cad_iterations_no_matching_files(self, tmp_path: Path):
        """Tests handling when directory contains files that do not match the versioning regex."""
        cad_dir = tmp_path / "cad"
        cad_dir.mkdir()
        (cad_dir / "readme.txt").write_text("info")
        (cad_dir / "bracket.step").write_text("cad data")
        (cad_dir / "subfolder").mkdir()  # Non-file item check

        manager = CADManager()
        result = manager.sweep_cad_iterations(params={"base_path": str(tmp_path)})
        assert f"No versioned CAD iterations (e.g. *_v1.step) found in {tmp_path}" in result

    def test_sweep_cad_iterations_single_version_no_archiving(self, tmp_path: Path):
        """Tests that single-version CAD files are kept intact and not moved to archive."""
        cad_dir = tmp_path / "cad"
        cad_dir.mkdir()
        (cad_dir / "mount_v1.step").write_text("v1 content")

        manager = CADManager()
        result = manager.sweep_cad_iterations(params={"base_path": str(tmp_path)})
        assert "All CAD files in" in result
        assert "are up to date. No deprecated iterations swept." in result
        assert not (cad_dir / "archive").exists()

    def test_sweep_cad_iterations_multiple_versions_success(self, tmp_path: Path):
        """Tests sweeping older CAD versions into the archive directory."""
        cad_dir = tmp_path / "cad"
        cad_dir.mkdir()

        # Group 1: mount
        v1 = cad_dir / "mount_v1.step"
        v2 = cad_dir / "mount_v2.step"
        v3 = cad_dir / "mount_v3.step"
        v1.write_text("v1")
        v2.write_text("v2")
        v3.write_text("v3")

        # Group 2: case
        c1 = cad_dir / "case-v1.stl"
        c2 = cad_dir / "case-v2.stl"
        c1.write_text("c1")
        c2.write_text("c2")

        manager = CADManager()
        # Updated target_path to base_path
        payload = CleanerPayload(action="sweep_cad_iterations", base_path=str(tmp_path))
        result = manager.sweep_cad_iterations(payload=payload)

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "Action : CAD Iteration Sweep" in result
        assert "mount_v1.step -> archive/mount_v1.step" in result
        assert "mount_v2.step -> archive/mount_v2.step" in result
        assert "case-v1.stl -> archive/case-v1.stl" in result

        archive_dir = cad_dir / "archive"
        assert (archive_dir / "mount_v1.step").exists()
        assert (archive_dir / "mount_v2.step").exists()
        assert (archive_dir / "case-v1.stl").exists()

        # Latest versions must remain in main CAD directory
        assert v3.exists()
        assert c2.exists()
