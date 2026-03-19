"""Tests for InstanceService: project-scoped SA/team instance lifecycle."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.db.project_sa_instances import (
    create_project_sa_instance,
    get_project_sa_instance,
    get_project_sa_instance_by_project_and_sa,
    update_project_sa_instance,
)
from app.db.project_team_instances import get_project_team_instance
from app.db.projects import create_project, update_project
from app.db.super_agents import (
    add_super_agent_session,
    create_super_agent,
    get_sessions_for_instance,
    get_super_agent_session,
)
from app.db.teams import add_team_member, create_team
from app.services.instance_service import InstanceService
from app.services.super_agent_session_service import SuperAgentSessionService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_session_state():
    """Reset SuperAgentSessionService in-memory state between tests."""
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


def _make_run_result(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _create_project_with_path(name="Test Project", local_path="/fake/repo"):
    """Helper to create a project with a local_path."""
    proj_id = create_project(name=name, local_path=local_path)
    return proj_id


def _create_sa(name="Test SA"):
    """Helper to create a super agent."""
    return create_super_agent(name=name, backend_type="claude")


def _create_team_with_sa_members(team_name="Test Team", sa_count=2):
    """Create a team with super_agent members, return (team_id, [sa_ids])."""
    team_id = create_team(name=team_name)
    sa_ids = []
    for i in range(sa_count):
        sa_id = create_super_agent(name=f"SA {i}", backend_type="claude")
        sa_ids.append(sa_id)
        add_team_member(team_id=team_id, super_agent_id=sa_id, name=f"SA {i}")
    return team_id, sa_ids


# ===========================================================================
# create_sa_instance
# ===========================================================================


class TestCreateSaInstance:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_instance_with_worktree(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """create_sa_instance creates DB row, worktree, and session."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa()

        result = InstanceService.create_sa_instance(proj_id, sa_id)

        assert result is not None
        assert result["id"].startswith("psa-")
        assert result["template_sa_id"] == sa_id
        assert result["worktree_path"] is not None
        assert result["session_id"] is not None

        # Verify DB row
        instance = get_project_sa_instance(result["id"])
        assert instance is not None
        assert instance["worktree_path"] is not None

    def test_returns_none_for_missing_project(self, isolated_db):
        """create_sa_instance returns None if project doesn't exist."""
        sa_id = _create_sa()
        result = InstanceService.create_sa_instance("proj-nonexist", sa_id)
        assert result is None

    def test_returns_none_for_missing_sa(self, isolated_db):
        """create_sa_instance returns None if super_agent doesn't exist."""
        proj_id = _create_project_with_path()
        result = InstanceService.create_sa_instance(proj_id, "super-nonexist")
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_idempotent_returns_existing(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """create_sa_instance returns existing instance on duplicate creation."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa()

        result1 = InstanceService.create_sa_instance(proj_id, sa_id)
        result2 = InstanceService.create_sa_instance(proj_id, sa_id)

        assert result1 is not None
        assert result2 is not None
        assert result2["id"] == result1["id"]

    def test_no_worktree_when_no_local_path(self, isolated_db):
        """create_sa_instance still works without local_path (worktree_path=None)."""
        proj_id = create_project(name="No Path Project")
        sa_id = _create_sa()

        result = InstanceService.create_sa_instance(proj_id, sa_id)

        assert result is not None
        assert result["worktree_path"] is None
        assert result["session_id"] is not None


# ===========================================================================
# create_team_instances
# ===========================================================================


class TestCreateTeamInstances:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_team_and_sa_instances(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """create_team_instances creates team instance + SA instances."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        team_id, sa_ids = _create_team_with_sa_members()

        result = InstanceService.create_team_instances(proj_id, team_id)

        assert result is not None
        assert result["team_instance_id"].startswith("pti-")
        assert len(result["sa_instances"]) == 2

        # Verify team instance in DB
        team_inst = get_project_team_instance(result["team_instance_id"])
        assert team_inst is not None
        assert team_inst["project_id"] == proj_id
        assert team_inst["template_team_id"] == team_id

        # Verify SA instances
        for sa_inst in result["sa_instances"]:
            assert sa_inst["id"].startswith("psa-")
            assert sa_inst["template_sa_id"] in sa_ids

    def test_returns_none_for_missing_project(self, isolated_db):
        """create_team_instances returns None for nonexistent project."""
        team_id, _ = _create_team_with_sa_members()
        result = InstanceService.create_team_instances("proj-nonexist", team_id)
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_skips_non_sa_members(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """create_team_instances skips members without super_agent_id."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        team_id = create_team(name="Mixed Team")
        sa_id = _create_sa(name="Real SA")
        add_team_member(team_id=team_id, super_agent_id=sa_id, name="SA Member")
        add_team_member(team_id=team_id, name="Manual Member")

        result = InstanceService.create_team_instances(proj_id, team_id)

        assert result is not None
        assert len(result["sa_instances"]) == 1
        assert result["sa_instances"][0]["template_sa_id"] == sa_id

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_handles_empty_team(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """create_team_instances handles team with no members."""
        proj_id = _create_project_with_path()
        team_id = create_team(name="Empty Team")

        result = InstanceService.create_team_instances(proj_id, team_id)

        assert result is not None
        assert result["team_instance_id"].startswith("pti-")
        assert len(result["sa_instances"]) == 0


# ===========================================================================
# ensure_manager_instance
# ===========================================================================


class TestEnsureManagerInstance:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_when_not_exists(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """ensure_manager_instance creates instance when none exists."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa(name="Manager SA")
        update_project(proj_id, manager_super_agent_id=sa_id)

        result = InstanceService.ensure_manager_instance(proj_id)

        assert result is not None
        assert result["template_sa_id"] == sa_id

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_returns_existing(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """ensure_manager_instance returns existing instance."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa(name="Manager SA")
        update_project(proj_id, manager_super_agent_id=sa_id)

        result1 = InstanceService.ensure_manager_instance(proj_id)
        result2 = InstanceService.ensure_manager_instance(proj_id)

        assert result1["id"] == result2["id"]

    def test_returns_none_when_no_manager(self, isolated_db):
        """ensure_manager_instance returns None when no manager SA set."""
        proj_id = _create_project_with_path()
        result = InstanceService.ensure_manager_instance(proj_id)
        assert result is None


# ===========================================================================
# cleanup_manager_instance
# ===========================================================================


class TestCleanupManagerInstance:
    @patch("app.services.instance_service.InstanceService._remove_worktree")
    def test_deletes_instance(self, mock_remove, isolated_db):
        """cleanup_manager_instance deletes the manager instance."""
        mock_remove.return_value = True

        proj_id = _create_project_with_path()
        sa_id = _create_sa(name="Old Manager")
        psa_id = create_project_sa_instance(proj_id, sa_id)
        assert psa_id is not None

        result = InstanceService.cleanup_manager_instance(proj_id, sa_id)
        assert result is True
        assert get_project_sa_instance(psa_id) is None

    def test_returns_false_when_not_found(self, isolated_db):
        """cleanup_manager_instance returns False when no instance found."""
        proj_id = _create_project_with_path()
        result = InstanceService.cleanup_manager_instance(proj_id, "super-nonexist")
        assert result is False


# ===========================================================================
# delete_instance
# ===========================================================================


class TestDeleteInstance:
    @patch("app.services.instance_service.InstanceService._remove_worktree")
    def test_deletes_with_worktree_and_sessions(self, mock_remove, isolated_db):
        """delete_instance ends sessions, removes worktree, deletes DB row."""
        mock_remove.return_value = True

        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id, worktree_path="/tmp/wt")

        # Create a session linked to this instance
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        result = InstanceService.delete_instance(psa_id)
        assert result is True

        # Instance should be gone
        assert get_project_sa_instance(psa_id) is None

        # Worktree removal should have been called
        mock_remove.assert_called_once_with("/tmp/wt")

        # Session should be ended
        session = get_super_agent_session(session_id)
        assert session["status"] == "completed"

    def test_returns_false_for_nonexistent(self, isolated_db):
        """delete_instance returns False for nonexistent instance."""
        result = InstanceService.delete_instance("psa-nonexist")
        assert result is False

    @patch("app.services.instance_service.InstanceService._remove_worktree")
    def test_deletes_without_worktree(self, mock_remove, isolated_db):
        """delete_instance works when no worktree is set."""
        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id)

        result = InstanceService.delete_instance(psa_id)
        assert result is True
        mock_remove.assert_not_called()


# ===========================================================================
# ensure_worktrees
# ===========================================================================


class TestEnsureWorktrees:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_missing_worktrees(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """ensure_worktrees creates worktrees for instances without one."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id)

        # Instance should have NULL worktree_path
        inst = get_project_sa_instance(psa_id)
        assert inst["worktree_path"] is None

        created = InstanceService.ensure_worktrees()
        assert created >= 1

        # Now should have a worktree_path
        inst = get_project_sa_instance(psa_id)
        assert inst["worktree_path"] is not None

    def test_returns_zero_when_all_have_worktrees(self, isolated_db):
        """ensure_worktrees returns 0 when all instances have worktrees."""
        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id, worktree_path="/already/set")

        created = InstanceService.ensure_worktrees()
        assert created == 0


# ===========================================================================
# ensure_worktree (single)
# ===========================================================================


class TestEnsureWorktree:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_worktree_for_instance(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """ensure_worktree creates worktree and updates DB."""
        mock_isdir.side_effect = lambda p: p == "/fake/repo" or False
        mock_run.return_value = _make_run_result()

        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id)

        path = InstanceService.ensure_worktree(psa_id)
        assert path is not None

        inst = get_project_sa_instance(psa_id)
        assert inst["worktree_path"] == path

    def test_returns_none_for_nonexistent(self, isolated_db):
        """ensure_worktree returns None for nonexistent instance."""
        result = InstanceService.ensure_worktree("psa-nonexist")
        assert result is None


# ===========================================================================
# _create_worktree
# ===========================================================================


class TestCreateWorktree:
    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_creates_worktree_successfully(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree runs git worktree add and returns path."""
        mock_isdir.side_effect = lambda p: p == "/repo" or False
        mock_run.return_value = _make_run_result()

        path = InstanceService._create_worktree("/repo", "My Agent", "psa-abc123")

        assert path == os.path.join("/repo", ".worktrees", "my-agent")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["git", "-C", "/repo"]
        assert "worktree" in cmd
        assert "-b" in cmd
        assert "instance/psa-abc123" in cmd

    def test_returns_none_for_empty_path(self, isolated_db):
        """_create_worktree returns None for empty project path."""
        result = InstanceService._create_worktree("", "agent", "psa-x")
        assert result is None

    @patch("app.services.instance_service.os.path.isdir", return_value=False)
    def test_returns_none_for_missing_dir(self, mock_isdir, isolated_db):
        """_create_worktree returns None when project dir doesn't exist."""
        result = InstanceService._create_worktree("/nonexistent", "agent", "psa-x")
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=False)
    @patch("app.services.instance_service.os.path.isdir", return_value=True)
    def test_returns_none_for_non_git_repo(self, mock_isdir, mock_exists, isolated_db):
        """_create_worktree returns None when .git doesn't exist."""
        result = InstanceService._create_worktree("/repo", "agent", "psa-x")
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_returns_none_on_git_failure(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree returns None on git command failure."""
        mock_isdir.side_effect = lambda p: p == "/repo" or False
        mock_run.return_value = _make_run_result(returncode=1, stderr="fatal: error")

        result = InstanceService._create_worktree("/repo", "agent", "psa-x")
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_retries_when_branch_exists(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree retries without -b when branch already exists."""
        mock_isdir.side_effect = lambda p: p == "/repo" or False
        mock_run.side_effect = [
            _make_run_result(returncode=1, stderr="already exists"),
            _make_run_result(),
        ]

        result = InstanceService._create_worktree("/repo", "agent", "psa-x")
        assert result is not None
        assert mock_run.call_count == 2
        # Second call should not have -b
        second_cmd = mock_run.call_args_list[1][0][0]
        assert "-b" not in second_cmd

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_reuses_existing_worktree_dir(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree returns path if worktree dir already exists."""
        # First call for project dir check, second for worktree dir check
        mock_isdir.return_value = True

        result = InstanceService._create_worktree("/repo", "agent", "psa-x")
        assert result == os.path.join("/repo", ".worktrees", "agent")
        mock_run.assert_not_called()

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_handles_timeout(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree returns None on subprocess timeout."""
        mock_isdir.side_effect = lambda p: p == "/repo" or False
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

        result = InstanceService._create_worktree("/repo", "agent", "psa-x")
        assert result is None

    @patch("app.services.instance_service.os.path.exists", return_value=True)
    @patch("app.services.instance_service.os.path.isdir")
    @patch("app.services.instance_service.subprocess.run")
    def test_lowercases_and_hyphenates_name(self, mock_run, mock_isdir, mock_exists, isolated_db):
        """_create_worktree converts SA name to lowercase with hyphens."""
        mock_isdir.side_effect = lambda p: p == "/repo" or False
        mock_run.return_value = _make_run_result()

        path = InstanceService._create_worktree("/repo", "My Cool Agent", "psa-x")
        assert path == os.path.join("/repo", ".worktrees", "my-cool-agent")


# ===========================================================================
# _remove_worktree
# ===========================================================================


class TestRemoveWorktree:
    @patch("app.services.instance_service.subprocess.run")
    def test_removes_successfully(self, mock_run, isolated_db):
        """_remove_worktree calls git worktree remove --force."""
        mock_run.return_value = _make_run_result()

        result = InstanceService._remove_worktree("/repo/.worktrees/agent")
        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "worktree", "remove", "--force", "/repo/.worktrees/agent"]

    @patch("app.services.instance_service.subprocess.run")
    def test_returns_false_on_failure(self, mock_run, isolated_db):
        """_remove_worktree returns False on git command failure."""
        mock_run.return_value = _make_run_result(returncode=1, stderr="not a worktree")

        result = InstanceService._remove_worktree("/bad/path")
        assert result is False

    @patch("app.services.instance_service.subprocess.run")
    def test_handles_timeout(self, mock_run, isolated_db):
        """_remove_worktree returns False on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

        result = InstanceService._remove_worktree("/repo/.worktrees/agent")
        assert result is False


# ===========================================================================
# DB helper: get_project_sa_instance_by_project_and_sa
# ===========================================================================


class TestGetByProjectAndSa:
    def test_finds_existing(self, isolated_db):
        """get_project_sa_instance_by_project_and_sa finds existing combo."""
        proj_id = _create_project_with_path()
        sa_id = _create_sa()
        psa_id = create_project_sa_instance(proj_id, sa_id)

        result = get_project_sa_instance_by_project_and_sa(proj_id, sa_id)
        assert result is not None
        assert result["id"] == psa_id

    def test_returns_none_when_not_found(self, isolated_db):
        """get_project_sa_instance_by_project_and_sa returns None for unknown combo."""
        result = get_project_sa_instance_by_project_and_sa("proj-x", "super-y")
        assert result is None


# ===========================================================================
# SuperAgentSessionService.create_session with instance_id
# ===========================================================================


class TestSessionCreateWithInstanceId:
    def test_session_stores_instance_id(self, isolated_db):
        """create_session with instance_id persists to DB."""
        sa_id = _create_sa()
        proj_id = _create_project_with_path()
        psa_id = create_project_sa_instance(proj_id, sa_id)

        session_id, error = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)
        assert error is None
        assert session_id is not None

        session = get_super_agent_session(session_id)
        assert session["instance_id"] == psa_id

    def test_session_without_instance_id(self, isolated_db):
        """create_session without instance_id stores NULL."""
        sa_id = _create_sa()

        session_id, error = SuperAgentSessionService.create_session(sa_id)
        assert error is None

        session = get_super_agent_session(session_id)
        assert session["instance_id"] is None
