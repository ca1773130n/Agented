"""Tests for GitOps sync engine and management routes.

All git operations are mocked -- no real cloning or remote access.
"""

import json
import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.db.gitops import (
    add_sync_log,
    create_gitops_repo,
    delete_gitops_repo,
    get_gitops_repo,
    list_gitops_repos,
    list_sync_logs,
    update_gitops_repo,
    update_sync_state,
)
from app.services.gitops_sync_service import GitOpsSyncService


# ---------------------------------------------------------------------------
# DB CRUD tests
# ---------------------------------------------------------------------------


class TestGitOpsRepoCRUD:
    """Test GitOps repo database operations."""

    def test_create_and_get_repo(self, isolated_db):
        repo_id = create_gitops_repo(
            name="test-repo",
            repo_url="https://github.com/test/repo.git",
            branch="main",
            config_path="agented/",
            poll_interval=120,
        )
        assert repo_id.startswith("gop-")

        repo = get_gitops_repo(repo_id)
        assert repo is not None
        assert repo["name"] == "test-repo"
        assert repo["repo_url"] == "https://github.com/test/repo.git"
        assert repo["branch"] == "main"
        assert repo["config_path"] == "agented/"
        assert repo["poll_interval_seconds"] == 120
        assert repo["enabled"] == 1

    def test_list_repos(self, isolated_db):
        create_gitops_repo("repo-a", "https://example.com/a.git")
        create_gitops_repo("repo-b", "https://example.com/b.git")
        repos = list_gitops_repos()
        assert len(repos) == 2

    def test_update_repo(self, isolated_db):
        repo_id = create_gitops_repo("old-name", "https://example.com/repo.git")
        updated = update_gitops_repo(repo_id, name="new-name", branch="develop")
        assert updated is True

        repo = get_gitops_repo(repo_id)
        assert repo["name"] == "new-name"
        assert repo["branch"] == "develop"

    def test_update_nonexistent_repo(self, isolated_db):
        result = update_gitops_repo("gop-nonexistent", name="test")
        assert result is False

    def test_delete_repo(self, isolated_db):
        repo_id = create_gitops_repo("delete-me", "https://example.com/repo.git")
        assert delete_gitops_repo(repo_id) is True
        assert get_gitops_repo(repo_id) is None

    def test_delete_nonexistent_repo(self, isolated_db):
        assert delete_gitops_repo("gop-nonexistent") is False

    def test_update_sync_state(self, isolated_db):
        repo_id = create_gitops_repo("sync-test", "https://example.com/repo.git")
        update_sync_state(repo_id, "abc123", "2026-03-05T00:00:00Z")

        repo = get_gitops_repo(repo_id)
        assert repo["last_commit_sha"] == "abc123"
        assert repo["last_sync_at"] == "2026-03-05T00:00:00Z"

    def test_sync_log_crud(self, isolated_db):
        repo_id = create_gitops_repo("log-test", "https://example.com/repo.git")
        log_id = add_sync_log(
            repo_id=repo_id,
            commit_sha="def456",
            files_changed=3,
            files_applied=2,
            files_conflicted=1,
            status="success",
            details=json.dumps({"test": True}),
        )
        assert log_id > 0

        logs = list_sync_logs(repo_id)
        assert len(logs) == 1
        assert logs[0]["commit_sha"] == "def456"
        assert logs[0]["files_changed"] == 3
        assert logs[0]["files_applied"] == 2
        assert logs[0]["files_conflicted"] == 1
        assert logs[0]["status"] == "success"


# ---------------------------------------------------------------------------
# Sync service tests
# ---------------------------------------------------------------------------


def _make_trigger_yaml(name="test-trigger", prompt="test prompt"):
    """Create a valid trigger YAML config string."""
    config = {
        "version": "1.0",
        "kind": "trigger",
        "metadata": {
            "name": name,
            "backend_type": "claude",
            "trigger_source": "webhook",
        },
        "spec": {
            "prompt_template": prompt,
            "detection_keyword": "",
        },
    }
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


class TestGitOpsSyncService:
    """Test GitOps sync engine with mocked git operations."""

    def _mock_git_clone(self, tmp_path, configs):
        """Set up a fake repo clone directory with config files.

        Args:
            tmp_path: Temp directory for the clone.
            configs: Dict of filename -> yaml_content.

        Returns:
            Callable that mocks subprocess.run for git operations.
        """
        # Create the clone dir with .git marker and config files
        clone_dir = tmp_path / "clone"
        git_dir = clone_dir / ".git"
        git_dir.mkdir(parents=True)
        config_dir = clone_dir / "agented"
        config_dir.mkdir(parents=True)

        for filename, content in configs.items():
            (config_dir / filename).write_text(content)

        return clone_dir

    @patch("app.services.gitops_sync_service.subprocess.run")
    @patch("app.services.gitops_sync_service._CACHE_BASE")
    def test_sync_detects_new_config(self, mock_cache, mock_run, isolated_db, tmp_path):
        """Test sync detects a new config file and imports it."""
        repo_id = create_gitops_repo("sync-new", "https://example.com/repo.git")

        # Set up fake clone directory
        clone_dir = self._mock_git_clone(tmp_path, {
            "bot-test.yaml": _make_trigger_yaml("sync-bot", "sync prompt"),
        })
        mock_cache.__str__ = lambda self: str(tmp_path / "cache")
        # Patch _get_local_path to return our fake clone
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            # Mock git operations
            mock_run.return_value = MagicMock(
                stdout="abc123def456\n", stderr="", returncode=0
            )

            result = GitOpsSyncService.sync_repo(repo_id)

        assert result["status"] == "success"
        assert result["commit_sha"] == "abc123def456"
        assert result["files_changed"] >= 1
        assert result["files_applied"] >= 1

        # Verify the trigger was created
        from app.db import get_trigger_by_name
        trigger = get_trigger_by_name("sync-bot")
        assert trigger is not None
        assert trigger["prompt_template"] == "sync prompt"

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_sync_skips_when_no_changes(self, mock_run, isolated_db, tmp_path):
        """Test sync skips when commit SHA hasn't changed."""
        repo_id = create_gitops_repo("skip-test", "https://example.com/repo.git")
        # Set last_commit_sha to match what git will return
        update_sync_state(repo_id, "same_sha", "2026-03-05T00:00:00Z")

        clone_dir = self._mock_git_clone(tmp_path, {})
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="same_sha\n", stderr="", returncode=0
            )
            result = GitOpsSyncService.sync_repo(repo_id)

        assert result["status"] == "skipped"
        assert result["files_changed"] == 0

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_sync_upserts_changed_config(self, mock_run, isolated_db, tmp_path):
        """Test sync updates existing trigger via upsert instead of creating duplicate."""
        repo_id = create_gitops_repo("upsert-test", "https://example.com/repo.git")

        # First sync: create the trigger
        clone_dir = self._mock_git_clone(tmp_path, {
            "bot-upsert.yaml": _make_trigger_yaml("upsert-bot", "original prompt"),
        })
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="sha1\n", stderr="", returncode=0
            )
            result1 = GitOpsSyncService.sync_repo(repo_id)

        assert result1["files_applied"] >= 1

        from app.db import get_trigger_by_name, get_all_triggers
        trigger_v1 = get_trigger_by_name("upsert-bot")
        assert trigger_v1 is not None
        original_id = trigger_v1["id"]

        # Second sync: update the trigger with different content
        config_dir = clone_dir / "agented"
        (config_dir / "bot-upsert.yaml").write_text(
            _make_trigger_yaml("upsert-bot", "updated prompt")
        )

        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="sha2\n", stderr="", returncode=0
            )
            result2 = GitOpsSyncService.sync_repo(repo_id)

        assert result2["files_applied"] >= 1

        # Verify upsert: same trigger updated, not duplicated
        trigger_v2 = get_trigger_by_name("upsert-bot")
        assert trigger_v2["id"] == original_id
        assert trigger_v2["prompt_template"] == "updated prompt"

        # No duplicates
        all_triggers = get_all_triggers()
        upsert_triggers = [t for t in all_triggers if t["name"] == "upsert-bot"]
        assert len(upsert_triggers) == 1

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_dry_run_shows_changes_without_applying(self, mock_run, isolated_db, tmp_path):
        """Test dry-run returns changes without applying them."""
        repo_id = create_gitops_repo("dry-run-test", "https://example.com/repo.git")

        clone_dir = self._mock_git_clone(tmp_path, {
            "bot-dry.yaml": _make_trigger_yaml("dry-run-bot", "dry prompt"),
        })
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="drysha\n", stderr="", returncode=0
            )
            result = GitOpsSyncService.sync_repo(repo_id, dry_run=True)

        assert result["status"] == "dry_run"
        assert result["files_changed"] >= 1
        assert result["files_applied"] == 0

        # Trigger should NOT exist
        from app.db import get_trigger_by_name
        assert get_trigger_by_name("dry-run-bot") is None

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_conflict_detection(self, mock_run, isolated_db, tmp_path):
        """Test conflict detection when both DB and Git changed."""
        repo_id = create_gitops_repo("conflict-test", "https://example.com/repo.git")

        # First sync to establish baseline
        clone_dir = self._mock_git_clone(tmp_path, {
            "bot-conflict.yaml": _make_trigger_yaml("conflict-bot", "v1 prompt"),
        })
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="sha-v1\n", stderr="", returncode=0
            )
            GitOpsSyncService.sync_repo(repo_id)

        # Now change BOTH sides: DB was modified, Git has different content
        from app.db import get_trigger_by_name, update_trigger
        trigger = get_trigger_by_name("conflict-bot")
        update_trigger(trigger["id"], prompt_template="db-modified prompt")

        # Update the Git file
        config_dir = clone_dir / "agented"
        (config_dir / "bot-conflict.yaml").write_text(
            _make_trigger_yaml("conflict-bot", "git-modified prompt")
        )

        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="sha-v2\n", stderr="", returncode=0
            )
            result = GitOpsSyncService.sync_repo(repo_id)

        assert result["status"] == "success"
        assert result["files_conflicted"] >= 1

        # Git wins: trigger should have git version
        trigger_after = get_trigger_by_name("conflict-bot")
        assert trigger_after["prompt_template"] == "git-modified prompt"

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_sync_disabled_repo_returns_disabled(self, mock_run, isolated_db):
        """Test that syncing a disabled repo returns disabled status."""
        repo_id = create_gitops_repo("disabled-test", "https://example.com/repo.git")
        update_gitops_repo(repo_id, enabled=0)

        result = GitOpsSyncService.sync_repo(repo_id)
        assert result["status"] == "disabled"
        mock_run.assert_not_called()

    def test_sync_nonexistent_repo_raises(self, isolated_db):
        """Test that syncing a nonexistent repo raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            GitOpsSyncService.sync_repo("gop-nonexistent")

    @patch("app.services.gitops_sync_service.subprocess.run")
    def test_sync_logs_created_after_sync(self, mock_run, isolated_db, tmp_path):
        """Test that sync log entries are created after sync."""
        repo_id = create_gitops_repo("log-sync", "https://example.com/repo.git")

        clone_dir = self._mock_git_clone(tmp_path, {
            "bot-log.yaml": _make_trigger_yaml("log-bot", "log prompt"),
        })
        with patch.object(GitOpsSyncService, "_get_local_path", return_value=str(clone_dir)):
            mock_run.return_value = MagicMock(
                stdout="logsha\n", stderr="", returncode=0
            )
            GitOpsSyncService.sync_repo(repo_id)

        logs = list_sync_logs(repo_id)
        assert len(logs) >= 1
        assert logs[0]["status"] == "success"
        assert logs[0]["commit_sha"] == "logsha"


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


class TestGitOpsRoutes:
    """Test GitOps management API endpoints."""

    def test_create_repo(self, client, isolated_db):
        resp = client.post(
            "/admin/gitops/repos",
            json={
                "name": "route-test",
                "repo_url": "https://github.com/test/repo.git",
                "branch": "main",
                "config_path": "config/",
                "poll_interval_seconds": 120,
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "route-test"
        assert data["repo_url"] == "https://github.com/test/repo.git"
        assert data["id"].startswith("gop-")

    def test_list_repos(self, client, isolated_db):
        create_gitops_repo("list-a", "https://example.com/a.git")
        create_gitops_repo("list-b", "https://example.com/b.git")

        resp = client.get("/admin/gitops/repos")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

    def test_get_repo(self, client, isolated_db):
        repo_id = create_gitops_repo("get-test", "https://example.com/repo.git")
        resp = client.get(f"/admin/gitops/repos/{repo_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "get-test"

    def test_get_nonexistent_repo(self, client, isolated_db):
        resp = client.get("/admin/gitops/repos/gop-nope")
        assert resp.status_code == 404

    def test_update_repo(self, client, isolated_db):
        repo_id = create_gitops_repo("update-test", "https://example.com/repo.git")
        resp = client.put(
            f"/admin/gitops/repos/{repo_id}",
            json={"name": "updated-name", "branch": "develop"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "updated-name"
        assert data["branch"] == "develop"

    def test_delete_repo(self, client, isolated_db):
        repo_id = create_gitops_repo("delete-test", "https://example.com/repo.git")
        resp = client.delete(f"/admin/gitops/repos/{repo_id}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/gitops/repos/{repo_id}")
        assert resp.status_code == 404

    @patch("app.routes.gitops.GitOpsSyncService.sync_repo")
    def test_trigger_sync(self, mock_sync, client, isolated_db):
        repo_id = create_gitops_repo("sync-route", "https://example.com/repo.git")
        mock_sync.return_value = {
            "commit_sha": "abc123",
            "files_changed": 1,
            "files_applied": 1,
            "files_conflicted": 0,
            "changes": [],
            "status": "success",
        }

        resp = client.post(f"/admin/gitops/repos/{repo_id}/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        mock_sync.assert_called_once_with(repo_id, dry_run=False)

    @patch("app.routes.gitops.GitOpsSyncService.sync_repo")
    def test_trigger_dry_run_sync(self, mock_sync, client, isolated_db):
        repo_id = create_gitops_repo("dry-route", "https://example.com/repo.git")
        mock_sync.return_value = {
            "commit_sha": "abc123",
            "files_changed": 2,
            "files_applied": 0,
            "files_conflicted": 0,
            "changes": [{"file": "test.yaml", "dry_run": True}],
            "status": "dry_run",
        }

        resp = client.post(f"/admin/gitops/repos/{repo_id}/sync?dry_run=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "dry_run"
        mock_sync.assert_called_once_with(repo_id, dry_run=True)

    def test_get_sync_logs(self, client, isolated_db):
        repo_id = create_gitops_repo("logs-route", "https://example.com/repo.git")
        add_sync_log(repo_id, "sha1", 1, 1, 0, "success")
        add_sync_log(repo_id, "sha2", 2, 2, 0, "success")

        resp = client.get(f"/admin/gitops/repos/{repo_id}/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

    def test_sync_nonexistent_repo(self, client, isolated_db):
        resp = client.post("/admin/gitops/repos/gop-nope/sync")
        assert resp.status_code == 404
