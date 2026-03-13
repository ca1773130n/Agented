"""Tests for TeamMonitorService and TeamFileHandler."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.team_monitor_service import TeamFileHandler, TeamMonitorService


@pytest.fixture(autouse=True)
def reset_monitors():
    """Reset class-level monitor state between tests."""
    TeamMonitorService._monitors.clear()
    yield
    TeamMonitorService._monitors.clear()


# ---------------------------------------------------------------------------
# _parse_team_config
# ---------------------------------------------------------------------------


class TestParseTeamConfig:
    def test_valid_json_with_members(self, tmp_path):
        config = {"name": "alpha", "members": [{"name": "alice"}, {"name": "bob"}]}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(config))

        result = TeamMonitorService._parse_team_config(str(p))

        assert result is not None
        assert result["name"] == "alpha"
        assert result["members"] == [{"name": "alice"}, {"name": "bob"}]
        assert result["config"] == config

    def test_valid_json_with_teammates_fallback(self, tmp_path):
        config = {"name": "beta", "teammates": ["c", "d"]}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(config))

        result = TeamMonitorService._parse_team_config(str(p))

        assert result is not None
        assert result["members"] == ["c", "d"]

    def test_valid_json_no_members_key(self, tmp_path):
        config = {"name": "gamma"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(config))

        result = TeamMonitorService._parse_team_config(str(p))

        assert result is not None
        assert result["members"] == []

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("not valid json {{{")

        assert TeamMonitorService._parse_team_config(str(p)) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert TeamMonitorService._parse_team_config(str(tmp_path / "nope.json")) is None


# ---------------------------------------------------------------------------
# _parse_task
# ---------------------------------------------------------------------------


class TestParseTask:
    def test_valid_task_json(self, tmp_path):
        task = {
            "id": "task-1",
            "status": "running",
            "assignee": "alice",
            "description": "Fix bug",
        }
        p = tmp_path / "task-1.json"
        p.write_text(json.dumps(task))

        result = TeamMonitorService._parse_task(str(p))

        assert result is not None
        assert result["id"] == "task-1"
        assert result["status"] == "running"
        assert result["assignee"] == "alice"
        assert result["description"] == "Fix bug"
        assert result["file"] == "task-1.json"

    def test_defaults_for_missing_fields(self, tmp_path):
        p = tmp_path / "task-2.json"
        p.write_text(json.dumps({}))

        result = TeamMonitorService._parse_task(str(p))

        assert result is not None
        assert result["id"] == ""
        assert result["status"] == "unknown"
        assert result["assignee"] == ""
        assert result["description"] == ""

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("<<<")

        assert TeamMonitorService._parse_task(str(p)) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert TeamMonitorService._parse_task(str(tmp_path / "no.json")) is None


# ---------------------------------------------------------------------------
# _update_members / _update_task / get_state
# ---------------------------------------------------------------------------


class TestStateHelpers:
    @staticmethod
    def _seed_state(session_id="sess-1", team_name="t1"):
        """Insert a minimal monitor entry for testing state helpers."""
        TeamMonitorService._monitors[session_id] = {
            "team_name": team_name,
            "members": [],
            "tasks": [],
            "active": True,
        }

    def test_update_members(self):
        self._seed_state()
        TeamMonitorService._update_members("sess-1", {"members": ["a", "b"]})

        state = TeamMonitorService._monitors["sess-1"]
        assert state["members"] == ["a", "b"]

    def test_update_members_unknown_session(self):
        # Should be a safe no-op
        TeamMonitorService._update_members("unknown", {"members": ["x"]})

    def test_update_task_appends_new(self):
        self._seed_state()
        TeamMonitorService._update_task("sess-1", {"id": "t1", "status": "done", "file": "t1.json"})

        tasks = TeamMonitorService._monitors["sess-1"]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["id"] == "t1"

    def test_update_task_replaces_existing(self):
        self._seed_state()
        TeamMonitorService._update_task(
            "sess-1", {"id": "t1", "status": "running", "file": "t1.json"}
        )
        TeamMonitorService._update_task("sess-1", {"id": "t1", "status": "done", "file": "t1.json"})

        tasks = TeamMonitorService._monitors["sess-1"]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done"

    def test_update_task_unknown_session(self):
        TeamMonitorService._update_task("unknown", {"id": "t1", "status": "done"})

    def test_get_state_returns_none_for_unknown(self):
        assert TeamMonitorService.get_state("no-such-session") is None

    def test_get_state_returns_copy(self):
        self._seed_state()
        TeamMonitorService._update_members("sess-1", {"members": ["a"]})
        TeamMonitorService._update_task("sess-1", {"id": "t1", "status": "ok", "file": "t.json"})

        result = TeamMonitorService.get_state("sess-1")

        assert result["team_name"] == "t1"
        assert result["members"] == ["a"]
        assert len(result["tasks"]) == 1
        # Returned lists should be copies
        result["members"].append("z")
        assert "z" not in TeamMonitorService._monitors["sess-1"]["members"]


# ---------------------------------------------------------------------------
# start_monitoring / stop_monitoring lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @patch("app.services.team_monitor_service.Observer")
    def test_start_and_stop(self, MockObserver, tmp_path, monkeypatch):
        mock_observer_instance = MagicMock()
        MockObserver.return_value = mock_observer_instance

        # Point home dir to tmp_path so dirs are created there
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        TeamMonitorService.start_monitoring("sess-a", "myteam")

        # Observer was started
        mock_observer_instance.start.assert_called_once()
        assert mock_observer_instance.daemon is True
        # Handler was scheduled for both directories
        assert mock_observer_instance.schedule.call_count == 2

        # State is accessible
        state = TeamMonitorService.get_state("sess-a")
        assert state is not None
        assert state["team_name"] == "myteam"

        # Directories were created
        assert (tmp_path / ".claude" / "teams" / "myteam").is_dir()
        assert (tmp_path / ".claude" / "tasks" / "myteam").is_dir()

        # Stop monitoring
        TeamMonitorService.stop_monitoring("sess-a")

        mock_observer_instance.stop.assert_called_once()
        mock_observer_instance.join.assert_called_once_with(timeout=5)
        assert TeamMonitorService.get_state("sess-a") is None

    def test_stop_unknown_session_is_noop(self):
        # Should not raise
        TeamMonitorService.stop_monitoring("nonexistent")


# ---------------------------------------------------------------------------
# TeamFileHandler._process_event
# ---------------------------------------------------------------------------


class TestTeamFileHandler:
    @patch("app.services.team_monitor_service.TeamMonitorService._update_members")
    @patch(
        "app.services.team_monitor_service.TeamMonitorService._parse_team_config",
        return_value={"members": ["a"]},
    )
    def test_process_config_event(self, mock_parse, mock_update, tmp_path):
        handler = TeamFileHandler("sess-1", "myteam")

        with patch("app.services.project_session_manager.ProjectSessionManager") as MockPSM:
            src = str(tmp_path / "myteam" / "config.json")
            handler._process_event(src)

            mock_parse.assert_called_once_with(src)
            mock_update.assert_called_once_with("sess-1", {"members": ["a"]})
            MockPSM._broadcast.assert_called_once_with(
                "sess-1",
                "team_update",
                {"type": "config", "data": {"members": ["a"]}},
            )

    @patch("app.services.team_monitor_service.TeamMonitorService._update_task")
    @patch(
        "app.services.team_monitor_service.TeamMonitorService._parse_task",
        return_value={"id": "t1", "status": "done"},
    )
    def test_process_task_event(self, mock_parse, mock_update, tmp_path):
        handler = TeamFileHandler("sess-1", "myteam")

        with patch("app.services.project_session_manager.ProjectSessionManager") as MockPSM:
            src = str(tmp_path / "tasks" / "myteam" / "task-1.json")
            handler._process_event(src)

            mock_parse.assert_called_once_with(src)
            mock_update.assert_called_once_with("sess-1", {"id": "t1", "status": "done"})
            MockPSM._broadcast.assert_called_once_with(
                "sess-1",
                "team_update",
                {"type": "task", "data": {"id": "t1", "status": "done"}},
            )

    def test_on_modified_ignores_directory(self):
        handler = TeamFileHandler("sess-1", "team")
        event = MagicMock()
        event.is_directory = True

        with patch.object(handler, "_process_event") as mock_proc:
            handler.on_modified(event)
            mock_proc.assert_not_called()

    def test_on_created_ignores_directory(self):
        handler = TeamFileHandler("sess-1", "team")
        event = MagicMock()
        event.is_directory = True

        with patch.object(handler, "_process_event") as mock_proc:
            handler.on_created(event)
            mock_proc.assert_not_called()

    def test_on_modified_delegates_to_process_event(self):
        handler = TeamFileHandler("sess-1", "team")
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/some/path/config.json"

        with patch.object(handler, "_process_event") as mock_proc:
            handler.on_modified(event)
            mock_proc.assert_called_once_with("/some/path/config.json")

    def test_on_created_delegates_to_process_event(self):
        handler = TeamFileHandler("sess-1", "team")
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/some/path/task.json"

        with patch.object(handler, "_process_event") as mock_proc:
            handler.on_created(event)
            mock_proc.assert_called_once_with("/some/path/task.json")

    def test_process_event_handles_exception_gracefully(self):
        handler = TeamFileHandler("sess-1", "myteam")

        with patch(
            "app.services.team_monitor_service.TeamMonitorService._parse_team_config",
            side_effect=RuntimeError("boom"),
        ):
            with patch("app.services.project_session_manager.ProjectSessionManager"):
                # Should not raise
                handler._process_event("/some/myteam/config.json")
