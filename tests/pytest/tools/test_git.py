import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.tools.git import git_commit, git_init


class TestGitInit:
    @patch("charon.tools.git.subprocess.run")
    def test_git_init_success(self, mock_run, tmp_path):
        success, msg = git_init(tmp_path)

        assert success is True
        assert msg == "Initialized successfully"
        mock_run.assert_called_once_with(
            ["git", "init"],
            cwd=tmp_path,
            check=True,
            capture_output=True
        )

    @patch("charon.tools.git.subprocess.run")
    def test_git_init_called_process_error(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "init"],
            stderr=b"fatal: cannot mkdir .git"
        )

        success, msg = git_init(tmp_path)

        assert success is False
        assert "fatal: cannot mkdir .git" in msg

    @patch("charon.tools.git.subprocess.run")
    def test_git_init_file_not_found(self, mock_run, tmp_path):
        mock_run.side_effect = FileNotFoundError()

        success, msg = git_init(tmp_path)

        assert success is False
        assert "Git executable not found on system" in msg


class TestGitCommit:
    def test_git_commit_no_git_dir(self, tmp_path):
        # Intentionally not creating a .git directory
        success, status, msg = git_commit(tmp_path, "Test commit")

        assert success is False
        assert status == "no_git"
        assert "not under Git version control" in msg

    @patch("charon.tools.git.subprocess.run")
    def test_git_commit_clean_workspace(self, mock_run, tmp_path):
        # Create a mock .git directory
        (tmp_path / ".git").mkdir()

        # Mock `git status --porcelain` returning empty output (clean workspace)
        mock_result = MagicMock()
        mock_result.stdout = b""
        mock_run.return_value = mock_result

        success, status, msg = git_commit(tmp_path, "Test commit")

        assert success is True
        assert status == "clean"
        assert "Skipped (Workspace is already clean)" in msg
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["git", "status", "--porcelain"]

    @patch("charon.tools.git.subprocess.run")
    def test_git_commit_success(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()

        # We need mock_run to return a dirty status on the first call,
        # and succeed on the add & commit calls.
        def run_side_effect(*args, **kwargs):
            mock_res = MagicMock()
            if "status" in args[0]:
                mock_res.stdout = b" M some_file.txt\n"
            else:
                mock_res.stdout = b""
            return mock_res

        mock_run.side_effect = run_side_effect

        success, status, msg = git_commit(tmp_path, "Initial commit")

        assert success is True
        assert status == "committed"
        assert msg == "Initial commit"
        assert mock_run.call_count == 3

        # Verify the sequence of commands
        calls = mock_run.call_args_list
        assert calls[0][0][0] == ["git", "status", "--porcelain"]
        assert calls[1][0][0] == ["git", "add", "."]
        assert calls[2][0][0] == ["git", "commit", "-m", "Initial commit"]
        # Verify they were all executed in the right directory
        for call in calls:
            assert call[1]["cwd"] == tmp_path

    @patch("charon.tools.git.subprocess.run")
    def test_git_commit_subprocess_error(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "commit"],
            stderr=b"Author identity unknown",
            output=b""  # Changed from stdout=b"" to output=b""
        )

        success, status, msg = git_commit(tmp_path, "Failing commit")

        assert success is False
        assert status == "failed"
        assert "Author identity unknown" in msg

    @patch("charon.tools.git.subprocess.run")
    def test_git_commit_file_not_found(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.side_effect = FileNotFoundError()

        success, status, msg = git_commit(tmp_path, "Will not commit")

        assert success is False
        assert status == "no_exe"
        assert "Git executable not found" in msg
