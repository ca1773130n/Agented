"""Unit tests for plugin_sync_service (SyncService + PluginFileWatcher)."""

import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.sync_persistence_service import SyncService
from app.services.plugin_file_watcher import PluginFileWatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


FAKE_AGENT = {
    "id": "agent-abc",
    "name": "Test Agent",
    "description": "A test agent",
    "system_prompt": "You are a test agent.",
}

FAKE_SKILL = {
    "id": 1,
    "skill_name": "code-review",
    "name": "code-review",
    "description": "Review code",
}

FAKE_COMMAND = {
    "id": 2,
    "name": "deploy",
    "description": "Deploy the app",
    "content": "Run deploy script",
    "arguments": "[]",
}


# ============================================================================
# _detect_entity_type
# ============================================================================


class TestDetectEntityType:
    def test_agent_md(self):
        assert SyncService._detect_entity_type("agents/my-agent.md") == "agent"

    def test_skill_md(self):
        assert SyncService._detect_entity_type("skills/code-review/SKILL.md") == "skill"

    def test_command_md(self):
        assert SyncService._detect_entity_type("commands/deploy.md") == "command"

    def test_hooks_json(self):
        assert SyncService._detect_entity_type("hooks/hooks.json") == "hook"

    def test_unrecognized_returns_none(self):
        assert SyncService._detect_entity_type("random/file.txt") is None

    def test_backslash_normalization(self):
        assert SyncService._detect_entity_type("agents\\my-agent.md") == "agent"


# ============================================================================
# _entity_file_path
# ============================================================================


class TestEntityFilePath:
    def test_agent_path(self):
        result = SyncService._entity_file_path("agent", {"name": "My Agent"}, "/plugins/p1")
        assert result == str(Path("/plugins/p1/agents/my-agent.md"))

    def test_skill_path(self):
        result = SyncService._entity_file_path(
            "skill", {"skill_name": "code-review"}, "/plugins/p1"
        )
        assert result == str(Path("/plugins/p1/skills/code-review/SKILL.md"))

    def test_command_path(self):
        result = SyncService._entity_file_path("command", {"name": "deploy"}, "/plugins/p1")
        assert result == str(Path("/plugins/p1/commands/deploy.md"))

    def test_unknown_type_returns_none(self):
        result = SyncService._entity_file_path("hook", {"name": "x"}, "/plugins/p1")
        assert result is None


# ============================================================================
# _load_entity
# ============================================================================


class TestLoadEntity:
    @patch("app.services.sync_persistence_service.get_agent", return_value=FAKE_AGENT)
    def test_load_agent(self, mock_get):
        result = SyncService._load_entity("agent", "agent-abc")
        assert result == FAKE_AGENT
        mock_get.assert_called_once_with("agent-abc")

    @patch("app.services.sync_persistence_service.get_user_skill", return_value=FAKE_SKILL)
    def test_load_skill(self, mock_get):
        result = SyncService._load_entity("skill", "1")
        assert result == FAKE_SKILL
        mock_get.assert_called_once_with(1)

    @patch("app.services.sync_persistence_service.get_command", return_value=FAKE_COMMAND)
    def test_load_command(self, mock_get):
        result = SyncService._load_entity("command", "2")
        assert result == FAKE_COMMAND
        mock_get.assert_called_once_with(2)

    def test_load_unknown_type_returns_none(self):
        assert SyncService._load_entity("unknown", "1") is None

    @patch("app.services.sync_persistence_service.get_agent", side_effect=ValueError("bad"))
    def test_load_entity_error_returns_none(self, _mock):
        assert SyncService._load_entity("agent", "bad-id") is None


# ============================================================================
# sync_entity_to_disk
# ============================================================================


class TestSyncEntityToDisk:
    @patch("app.services.sync_persistence_service.update_sync_state")
    @patch("app.services.sync_persistence_service.get_sync_state", return_value=None)
    @patch(
        "app.services.sync_persistence_service.generate_agent_md",
        return_value="# Agent\nHello",
    )
    @patch(
        "app.services.sync_persistence_service.get_agent",
        return_value=FAKE_AGENT,
    )
    def test_writes_file_when_no_prior_state(
        self, _get, _gen, _state, _update, tmp_path
    ):
        plugin_dir = str(tmp_path / "plugin")
        result = SyncService.sync_entity_to_disk("agent", "agent-abc", "plug-1", plugin_dir)
        assert result is True
        # File should exist on disk
        agent_file = tmp_path / "plugin" / "agents" / "test-agent.md"
        assert agent_file.exists()
        assert agent_file.read_text() == "# Agent\nHello"

    @patch("app.services.sync_persistence_service.get_sync_state")
    @patch(
        "app.services.sync_persistence_service.generate_agent_md",
        return_value="# Agent\nHello",
    )
    @patch(
        "app.services.sync_persistence_service.get_agent",
        return_value=FAKE_AGENT,
    )
    def test_skips_when_hash_matches(self, _get, _gen, mock_state, tmp_path):
        content = "# Agent\nHello"
        mock_state.return_value = {"content_hash": _sha256(content)}
        plugin_dir = str(tmp_path / "plugin")
        result = SyncService.sync_entity_to_disk("agent", "agent-abc", "plug-1", plugin_dir)
        assert result is False

    @patch("app.services.sync_persistence_service.get_agent", return_value=None)
    def test_returns_false_when_entity_not_found(self, _get, tmp_path):
        result = SyncService.sync_entity_to_disk(
            "agent", "agent-missing", "plug-1", str(tmp_path)
        )
        assert result is False


# ============================================================================
# sync_all_to_disk
# ============================================================================


class TestSyncAllToDisk:
    @patch.object(SyncService, "sync_entity_to_disk")
    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin")
    def test_aggregates_results(self, mock_states, mock_sync, tmp_path):
        mock_states.return_value = [
            {"entity_type": "agent", "entity_id": "agent-1"},
            {"entity_type": "skill", "entity_id": "2"},
            {"entity_type": "command", "entity_id": "3"},
        ]
        # First synced, second skipped, third errors
        mock_sync.side_effect = [True, False, Exception("boom")]
        result = SyncService.sync_all_to_disk("plug-1", str(tmp_path))
        assert result == {"synced": 1, "skipped": 1, "errors": 1}

    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin", return_value=[])
    def test_empty_plugin(self, _mock, tmp_path):
        result = SyncService.sync_all_to_disk("plug-1", str(tmp_path))
        assert result == {"synced": 0, "skipped": 0, "errors": 0}


# ============================================================================
# sync_file_to_db
# ============================================================================


class TestSyncFileToDb:
    @patch("app.services.sync_persistence_service.update_sync_state")
    @patch("app.services.sync_persistence_service.update_agent")
    @patch("app.services.sync_persistence_service.parse_yaml_frontmatter")
    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin")
    def test_syncs_agent_file_to_db(
        self, mock_states, mock_parse, mock_update, mock_sync_state, tmp_path
    ):
        plugin_dir = str(tmp_path)
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        agent_file = agent_dir / "my-agent.md"
        agent_file.write_text("---\nname: Updated\n---\nNew prompt")

        mock_states.return_value = [
            {
                "entity_type": "agent",
                "entity_id": "agent-abc",
                "file_path": str(agent_file),
                "content_hash": "old-hash",
            }
        ]
        mock_parse.return_value = ({"name": "Updated"}, "New prompt")

        result = SyncService.sync_file_to_db(str(agent_file), "plug-1", plugin_dir)
        assert result is True
        mock_update.assert_called_once_with("agent-abc", name="Updated", system_prompt="New prompt")

    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin", return_value=[])
    def test_returns_false_no_sync_state(self, _mock, tmp_path):
        plugin_dir = str(tmp_path)
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        agent_file = agent_dir / "test.md"
        agent_file.write_text("content")

        result = SyncService.sync_file_to_db(str(agent_file), "plug-1", plugin_dir)
        assert result is False

    def test_returns_false_for_unrecognized_path(self, tmp_path):
        plugin_dir = str(tmp_path)
        random_file = tmp_path / "random.txt"
        random_file.write_text("hello")
        result = SyncService.sync_file_to_db(str(random_file), "plug-1", plugin_dir)
        assert result is False


# ============================================================================
# get_sync_status
# ============================================================================


class TestGetSyncStatus:
    @patch.object(SyncService, "is_watching", return_value=False)
    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin")
    def test_returns_status_summary(self, mock_states, _watch):
        mock_states.return_value = [
            {
                "entity_type": "agent",
                "entity_id": "agent-1",
                "content_hash": "abc",
                "sync_direction": "to_disk",
                "last_synced_at": "2025-01-01T00:00:00",
            },
            {
                "entity_type": "skill",
                "entity_id": "2",
                "content_hash": "def",
                "sync_direction": "from_disk",
                "last_synced_at": "2025-06-01T00:00:00",
            },
        ]
        status = SyncService.get_sync_status("plug-1")
        assert status["plugin_id"] == "plug-1"
        assert status["entity_count"] == 2
        assert status["last_synced_at"] == "2025-06-01T00:00:00"
        assert status["watching"] is False
        assert len(status["entities"]) == 2

    @patch.object(SyncService, "is_watching", return_value=True)
    @patch(
        "app.services.sync_persistence_service.get_sync_states_for_plugin", return_value=[]
    )
    def test_empty_plugin_status(self, _states, _watch):
        status = SyncService.get_sync_status("plug-empty")
        assert status["entity_count"] == 0
        assert status["last_synced_at"] is None
        assert status["watching"] is True


# ============================================================================
# Watcher management (start/stop/is_watching)
# ============================================================================


class TestWatcherManagement:
    def setup_method(self):
        """Clear watcher registry before each test."""
        SyncService._watchers.clear()

    def teardown_method(self):
        """Stop any watchers left behind."""
        for watcher in SyncService._watchers.values():
            try:
                watcher.stop()
            except Exception:
                pass
        SyncService._watchers.clear()

    @patch("app.services.plugin_file_watcher.PluginFileWatcher")
    def test_start_watching(self, MockWatcher):
        mock_instance = MagicMock()
        MockWatcher.return_value = mock_instance

        SyncService.start_watching("plug-1", "/tmp/plugin")
        assert SyncService.is_watching("plug-1")
        mock_instance.start.assert_called_once()

    @patch("app.services.plugin_file_watcher.PluginFileWatcher")
    def test_start_watching_duplicate_ignored(self, MockWatcher):
        mock_instance = MagicMock()
        MockWatcher.return_value = mock_instance

        SyncService.start_watching("plug-1", "/tmp/plugin")
        SyncService.start_watching("plug-1", "/tmp/plugin")
        # Only one watcher created
        assert MockWatcher.call_count == 1

    @patch("app.services.plugin_file_watcher.PluginFileWatcher")
    def test_stop_watching(self, MockWatcher):
        mock_instance = MagicMock()
        MockWatcher.return_value = mock_instance

        SyncService.start_watching("plug-1", "/tmp/plugin")
        SyncService.stop_watching("plug-1")
        assert not SyncService.is_watching("plug-1")
        mock_instance.stop.assert_called_once()

    def test_stop_watching_nonexistent(self):
        """Stopping a non-existent watcher should not raise."""
        SyncService.stop_watching("plug-nonexistent")

    def test_is_watching_false_by_default(self):
        assert SyncService.is_watching("plug-unknown") is False


# ============================================================================
# PluginFileWatcher
# ============================================================================


class TestPluginFileWatcher:
    def test_on_modified_ignores_directories(self):
        watcher = PluginFileWatcher("plug-1", "/tmp/plugin")
        event = MagicMock()
        event.is_directory = True
        watcher.on_modified(event)
        assert len(watcher._pending) == 0

    def test_on_modified_records_file(self):
        watcher = PluginFileWatcher("plug-1", "/tmp/plugin")
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/plugin/agents/test.md"
        watcher.on_modified(event)
        assert "/tmp/plugin/agents/test.md" in watcher._pending
        # Clean up timer
        if watcher._timer:
            watcher._timer.cancel()

    def test_on_created_records_file(self):
        watcher = PluginFileWatcher("plug-1", "/tmp/plugin")
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/plugin/skills/new/SKILL.md"
        watcher.on_created(event)
        assert "/tmp/plugin/skills/new/SKILL.md" in watcher._pending
        if watcher._timer:
            watcher._timer.cancel()

    @patch.object(SyncService, "sync_file_to_db")
    def test_process_pending_calls_sync(self, mock_sync):
        watcher = PluginFileWatcher("plug-1", "/tmp/plugin")
        watcher._pending = {"/tmp/plugin/agents/test.md": 1234567890.0}
        watcher._process_pending()
        mock_sync.assert_called_once_with("/tmp/plugin/agents/test.md", "plug-1", "/tmp/plugin")
        assert len(watcher._pending) == 0

    @patch.object(SyncService, "sync_file_to_db")
    def test_process_pending_skips_syncing_paths(self, mock_sync):
        """Files currently being written by SyncService are skipped (loop prevention)."""
        watcher = PluginFileWatcher("plug-1", "/tmp/plugin")
        path = "/tmp/plugin/agents/test.md"
        SyncService._syncing_paths.add(path)
        try:
            watcher._pending = {path: 1234567890.0}
            watcher._process_pending()
            mock_sync.assert_not_called()
        finally:
            SyncService._syncing_paths.discard(path)


# ============================================================================
# _generate_hooks_bundle
# ============================================================================


class TestGenerateHooksBundle:
    @patch("app.services.sync_persistence_service.generate_hooks_json")
    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin")
    @patch.object(SyncService, "_load_entity")
    def test_generates_json(self, mock_load, mock_states, mock_gen):
        mock_states.return_value = [
            {"entity_type": "hook", "entity_id": "10"},
            {"entity_type": "rule", "entity_id": "20"},
        ]
        hook_entity = {"id": 10, "event": "push", "description": "On push"}
        rule_entity = {"id": 20, "description": "No secrets"}
        mock_load.side_effect = lambda t, eid: hook_entity if t == "hook" else rule_entity
        mock_gen.return_value = ({"hooks": [{"event": "push"}]}, [])

        content, path = SyncService._generate_hooks_bundle("plug-1", "/plugins/p1")
        assert path == str(Path("/plugins/p1/hooks/hooks.json"))
        parsed = json.loads(content)
        assert "hooks" in parsed

    @patch("app.services.sync_persistence_service.get_sync_states_for_plugin", return_value=[])
    def test_returns_none_when_no_hooks(self, _mock):
        content, path = SyncService._generate_hooks_bundle("plug-1", "/plugins/p1")
        assert content is None
        assert path is None
