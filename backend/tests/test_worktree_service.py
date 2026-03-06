"""Tests for WorktreeService: git worktree lifecycle management."""

import os
import subprocess
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from app.services.worktree_service import WorktreeService


@pytest.fixture(autouse=True)
def reset_worktree_locks():
    """Reset WorktreeService class-level lock state between tests."""
    WorktreeService._locks.clear()
    yield
    WorktreeService._locks.clear()


def _make_run_result(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# _get_project_lock
# ---------------------------------------------------------------------------


class TestGetProjectLock:
    def test_returns_same_lock_for_same_path(self):
        lock1 = WorktreeService._get_project_lock("/repo/a")
        lock2 = WorktreeService._get_project_lock("/repo/a")
        assert lock1 is lock2

    def test_returns_different_locks_for_different_paths(self):
        lock1 = WorktreeService._get_project_lock("/repo/a")
        lock2 = WorktreeService._get_project_lock("/repo/b")
        assert lock1 is not lock2


# ---------------------------------------------------------------------------
# list_worktrees
# ---------------------------------------------------------------------------


class TestListWorktrees:
    @patch("app.services.worktree_service.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = _make_run_result(returncode=1, stderr="not a git repo")
        result = WorktreeService.list_worktrees("/fake/repo")
        assert result == []

    @patch("app.services.worktree_service.subprocess.run")
    def test_parses_porcelain_output(self, mock_run):
        porcelain = (
            "worktree /repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo/.worktrees/phase-01-plan-01\n"
            "HEAD def456\n"
            "branch refs/heads/grd/phase-01-feature\n"
            "\n"
        )
        mock_run.return_value = _make_run_result(stdout=porcelain)
        result = WorktreeService.list_worktrees("/repo")
        assert len(result) == 1
        assert result[0]["path"] == "/repo/.worktrees/phase-01-plan-01"
        assert result[0]["head"] == "def456"
        assert result[0]["branch"] == "grd/phase-01-feature"

    @patch("app.services.worktree_service.subprocess.run")
    def test_filters_out_main_worktree(self, mock_run):
        porcelain = (
            "worktree /repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
        )
        mock_run.return_value = _make_run_result(stdout=porcelain)
        result = WorktreeService.list_worktrees("/repo")
        assert result == []

    @patch("app.services.worktree_service.subprocess.run")
    def test_parses_multiple_worktrees(self, mock_run):
        porcelain = (
            "worktree /repo\n"
            "HEAD abc\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /repo/.worktrees/wt1\n"
            "HEAD 111\n"
            "branch refs/heads/branch1\n"
            "\n"
            "worktree /repo/.worktrees/wt2\n"
            "HEAD 222\n"
            "branch refs/heads/branch2\n"
        )
        mock_run.return_value = _make_run_result(stdout=porcelain)
        result = WorktreeService.list_worktrees("/repo")
        assert len(result) == 2
        assert result[0]["path"] == "/repo/.worktrees/wt1"
        assert result[1]["path"] == "/repo/.worktrees/wt2"


# ---------------------------------------------------------------------------
# create_worktree
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_raises_when_limit_reached(self, mock_list, mock_gitignore, mock_run):
        mock_list.return_value = [{"path": f"/wt{i}"} for i in range(5)]
        with pytest.raises(RuntimeError, match="Concurrent worktree limit reached"):
            WorktreeService.create_worktree("/repo", "wt-new", "branch-new", limit=5)

    @patch("os.path.isdir", return_value=True)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_reuses_existing_worktree_dir(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = []
        mock_run.return_value = _make_run_result()  # git fetch
        result = WorktreeService.create_worktree("/repo", "wt1", "branch1")
        assert result == os.path.join("/repo", ".worktrees", "wt1")

    @patch("os.path.isdir", return_value=False)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_creates_new_worktree_successfully(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = []
        # First call: git fetch, second call: git worktree add
        mock_run.side_effect = [_make_run_result(), _make_run_result()]
        result = WorktreeService.create_worktree("/repo", "wt1", "branch1")
        assert result == os.path.join("/repo", ".worktrees", "wt1")
        # Verify git worktree add was called with -b
        add_call = mock_run.call_args_list[1]
        assert add_call[0][0][:4] == ["git", "worktree", "add", "-b"]

    @patch("os.path.isdir", return_value=False)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_retries_without_b_when_branch_exists(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = []
        fetch_ok = _make_run_result()
        branch_exists_err = _make_run_result(returncode=1, stderr="branch 'b1' already exists")
        retry_ok = _make_run_result()
        mock_run.side_effect = [fetch_ok, branch_exists_err, retry_ok]
        result = WorktreeService.create_worktree("/repo", "wt1", "b1")
        assert result == os.path.join("/repo", ".worktrees", "wt1")
        # Third call should be without -b
        retry_call = mock_run.call_args_list[2]
        assert "-b" not in retry_call[0][0]

    @patch("os.path.isdir", return_value=False)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_raises_on_git_worktree_add_failure(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = []
        mock_run.side_effect = [
            _make_run_result(),  # fetch
            _make_run_result(returncode=1, stderr="fatal: some error"),
        ]
        with pytest.raises(RuntimeError, match="Failed to create worktree"):
            WorktreeService.create_worktree("/repo", "wt1", "branch1")

    @patch("os.path.isdir", return_value=False)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_raises_on_retry_failure(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = []
        mock_run.side_effect = [
            _make_run_result(),  # fetch
            _make_run_result(returncode=1, stderr="already exists"),
            _make_run_result(returncode=1, stderr="fatal: locked"),
        ]
        with pytest.raises(RuntimeError, match="Failed to create worktree.*reuse branch"):
            WorktreeService.create_worktree("/repo", "wt1", "branch1")

    @patch("os.path.isdir", return_value=False)
    @patch("app.services.worktree_service.subprocess.run")
    @patch("app.services.worktree_service.WorktreeService._ensure_gitignore")
    @patch("app.services.worktree_service.WorktreeService.list_worktrees")
    def test_custom_limit(self, mock_list, mock_gitignore, mock_run, mock_isdir):
        mock_list.return_value = [{"path": "/wt0"}, {"path": "/wt1"}]
        with pytest.raises(RuntimeError, match="limit reached \\(2\\)"):
            WorktreeService.create_worktree("/repo", "wt-new", "branch-new", limit=2)


# ---------------------------------------------------------------------------
# remove_worktree
# ---------------------------------------------------------------------------


class TestRemoveWorktree:
    @patch("app.services.worktree_service.WorktreeService.prune_worktrees")
    @patch("app.services.worktree_service.subprocess.run")
    def test_remove_success(self, mock_run, mock_prune):
        mock_run.return_value = _make_run_result()
        mock_prune.return_value = True
        result = WorktreeService.remove_worktree("/repo", "/repo/.worktrees/wt1")
        assert result is True
        mock_prune.assert_called_once_with("/repo")

    @patch("app.services.worktree_service.subprocess.run")
    def test_remove_failure(self, mock_run):
        mock_run.return_value = _make_run_result(returncode=1, stderr="no such worktree")
        result = WorktreeService.remove_worktree("/repo", "/repo/.worktrees/gone")
        assert result is False


# ---------------------------------------------------------------------------
# prune_worktrees
# ---------------------------------------------------------------------------


class TestPruneWorktrees:
    @patch("app.services.worktree_service.subprocess.run")
    def test_prune_success(self, mock_run):
        mock_run.return_value = _make_run_result()
        assert WorktreeService.prune_worktrees("/repo") is True

    @patch("app.services.worktree_service.subprocess.run")
    def test_prune_failure(self, mock_run):
        mock_run.return_value = _make_run_result(returncode=1, stderr="error")
        assert WorktreeService.prune_worktrees("/repo") is False


# ---------------------------------------------------------------------------
# _ensure_gitignore
# ---------------------------------------------------------------------------


class TestEnsureGitignore:
    def test_creates_gitignore_when_missing(self, tmp_path):
        project = str(tmp_path)
        WorktreeService._ensure_gitignore(project)
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".worktrees/" in gitignore.read_text()

    def test_appends_when_not_present(self, tmp_path):
        project = str(tmp_path)
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")
        WorktreeService._ensure_gitignore(project)
        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".worktrees/" in content

    def test_skips_when_already_present(self, tmp_path):
        project = str(tmp_path)
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n.worktrees/\n")
        WorktreeService._ensure_gitignore(project)
        content = gitignore.read_text()
        # Should not duplicate the entry
        assert content.count(".worktrees/") == 1

    def test_recognizes_variant_without_slash(self, tmp_path):
        project = str(tmp_path)
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".worktrees\n")
        WorktreeService._ensure_gitignore(project)
        content = gitignore.read_text()
        # Should recognize .worktrees (without slash) and not append
        assert content.count(".worktrees") == 1


# ---------------------------------------------------------------------------
# get_worktree_for_plan
# ---------------------------------------------------------------------------


class TestGetWorktreeForPlan:
    @patch("app.services.worktree_service.WorktreeService.create_worktree")
    def test_generates_correct_names(self, mock_create):
        mock_create.return_value = "/repo/.worktrees/phase-05-plan-03"
        result = WorktreeService.get_worktree_for_plan(
            project_path="/repo",
            phase_number=5,
            plan_number=3,
            phase_slug="my-feature",
        )
        assert result == "/repo/.worktrees/phase-05-plan-03"
        mock_create.assert_called_once_with(
            project_path="/repo",
            worktree_name="phase-05-plan-03",
            branch_name="grd/phase-05-my-feature",
        )

    @patch("app.services.worktree_service.WorktreeService.create_worktree")
    def test_zero_pads_numbers(self, mock_create):
        mock_create.return_value = "/repo/.worktrees/phase-48-plan-01"
        WorktreeService.get_worktree_for_plan("/repo", 48, 1, "slug")
        mock_create.assert_called_once_with(
            project_path="/repo",
            worktree_name="phase-48-plan-01",
            branch_name="grd/phase-48-slug",
        )
