"""Unit tests for McpSyncService -- focused on sync logic, error handling, and edge cases."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.mcp_sync_service import McpSyncService


# ---------------------------------------------------------------------------
# transform_to_claude
# ---------------------------------------------------------------------------


class TestTransformToClaude:
    """Tests for the transform_to_claude static method."""

    def test_stdio_server_with_env(self):
        """Stdio server with non-empty env includes env key."""
        server = {
            "server_type": "stdio",
            "command": "node",
            "args": '["server.js"]',
            "env_json": '{"API_KEY": "secret123"}',
        }
        result = McpSyncService.transform_to_claude(server)

        assert result["_agented_managed"] is True
        assert result["command"] == "node"
        assert result["args"] == ["server.js"]
        assert result["env"] == {"API_KEY": "secret123"}

    def test_stdio_defaults_when_fields_missing(self):
        """Missing args and env_json default to empty list and no env key."""
        server = {"server_type": "stdio", "command": "my-tool"}
        result = McpSyncService.transform_to_claude(server)

        assert result["args"] == []
        assert "env" not in result

    def test_default_server_type_is_stdio(self):
        """When server_type is absent, defaults to stdio."""
        server = {"command": "npx", "args": "[]"}
        result = McpSyncService.transform_to_claude(server)

        assert result["command"] == "npx"
        assert "type" not in result  # stdio doesn't set 'type'

    def test_env_overrides_merge_and_win(self):
        """Env overrides merge with base env; override keys win over base."""
        server = {
            "server_type": "stdio",
            "command": "npx",
            "args": "[]",
            "env_json": '{"A": "1", "B": "2"}',
        }
        result = McpSyncService.transform_to_claude(server, '{"B": "override", "C": "3"}')

        assert result["env"] == {"A": "1", "B": "override", "C": "3"}

    def test_env_overrides_on_empty_base(self):
        """Env overrides applied even when base env is empty."""
        server = {
            "server_type": "stdio",
            "command": "npx",
            "args": "[]",
            "env_json": "{}",
        }
        result = McpSyncService.transform_to_claude(server, '{"TOKEN": "abc"}')

        assert result["env"] == {"TOKEN": "abc"}

    def test_http_server_with_headers(self):
        """HTTP server with headers includes them in output."""
        server = {
            "server_type": "http",
            "url": "https://example.com/mcp",
            "headers_json": '{"Authorization": "Bearer tok"}',
        }
        result = McpSyncService.transform_to_claude(server)

        assert result["type"] == "http"
        assert result["url"] == "https://example.com/mcp"
        assert result["headers"] == {"Authorization": "Bearer tok"}

    def test_sse_server_no_headers(self):
        """SSE server with no headers omits headers key."""
        server = {
            "server_type": "sse",
            "url": "http://localhost:9090/sse",
            "headers_json": None,
        }
        result = McpSyncService.transform_to_claude(server)

        assert result["type"] == "sse"
        assert result["url"] == "http://localhost:9090/sse"
        assert "headers" not in result


# ---------------------------------------------------------------------------
# build_merged_config
# ---------------------------------------------------------------------------


class TestBuildMergedConfig:
    """Tests for build_merged_config which queries DB and transforms servers."""

    def test_enabled_servers_included(self):
        """Enabled servers appear in the merged config."""
        servers = [
            {
                "server_name": "srv1",
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": "{}",
                "assignment_enabled": 1,
                "env_overrides_json": None,
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert "srv1" in result
        assert result["srv1"]["_agented_managed"] is True

    def test_disabled_servers_excluded(self):
        """Servers with assignment_enabled=0 are excluded."""
        servers = [
            {
                "server_name": "disabled",
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": "{}",
                "assignment_enabled": 0,
                "env_overrides_json": None,
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert result == {}

    def test_falls_back_to_enabled_field(self):
        """When assignment_enabled is absent, falls back to 'enabled' field."""
        servers = [
            {
                "server_name": "fallback",
                "server_type": "stdio",
                "command": "node",
                "args": "[]",
                "env_json": "{}",
                "enabled": 1,
                "env_overrides_json": None,
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert "fallback" in result

    def test_server_with_no_name_skipped(self):
        """Servers missing both server_name and name are skipped."""
        servers = [
            {
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": "{}",
                "assignment_enabled": 1,
                "env_overrides_json": None,
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert result == {}

    def test_uses_name_when_server_name_absent(self):
        """Falls back to 'name' field when 'server_name' is missing."""
        servers = [
            {
                "name": "by-name",
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": "{}",
                "assignment_enabled": 1,
                "env_overrides_json": None,
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert "by-name" in result

    def test_env_overrides_json_applied(self):
        """env_overrides_json from junction table is passed to transform."""
        servers = [
            {
                "server_name": "srv",
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": '{"BASE": "val"}',
                "assignment_enabled": 1,
                "env_overrides_json": '{"EXTRA": "override"}',
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert result["srv"]["env"]["BASE"] == "val"
        assert result["srv"]["env"]["EXTRA"] == "override"

    def test_config_override_fallback(self):
        """Falls back to config_override when env_overrides_json is absent."""
        servers = [
            {
                "server_name": "srv",
                "server_type": "stdio",
                "command": "npx",
                "args": "[]",
                "env_json": "{}",
                "assignment_enabled": 1,
                "config_override": '{"KEY": "val"}',
            },
        ]
        with patch("app.db.get_project_mcp_servers", return_value=servers):
            result = McpSyncService.build_merged_config("proj-abc")

        assert result["srv"]["env"] == {"KEY": "val"}


# ---------------------------------------------------------------------------
# sync_project
# ---------------------------------------------------------------------------


class TestSyncProject:
    """Tests for the sync_project method -- dry-run, write, error handling."""

    def test_no_existing_file_creates_new(self, tmp_path):
        """When .mcp.json doesn't exist, sync creates it from scratch."""
        agented = {"srv": {"_agented_managed": True, "command": "npx", "args": []}}

        with patch.object(McpSyncService, "build_merged_config", return_value=agented):
            result = McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        assert "written" in result
        assert result["servers"] == 1
        assert result["backup"] is None  # no pre-existing file

        content = json.loads((tmp_path / ".mcp.json").read_text())
        assert content["srv"]["_agented_managed"] is True

    def test_dry_run_no_file_change(self, tmp_path):
        """Dry-run with no existing file returns diff but writes nothing."""
        agented = {"srv": {"_agented_managed": True, "command": "npx", "args": []}}

        with patch.object(McpSyncService, "build_merged_config", return_value=agented):
            result = McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=True)

        assert "diff" in result
        assert result["servers_count"] == 1
        assert not (tmp_path / ".mcp.json").exists()

    def test_preserves_non_agented_entries(self, tmp_path):
        """Non-agented entries survive a sync; old agented entries are replaced."""
        existing = {
            "user-custom": {"command": "python", "args": ["-m", "custom"]},
            "old-agented": {"_agented_managed": True, "command": "old"},
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(existing))

        new_agented = {"new-srv": {"_agented_managed": True, "command": "new"}}

        with patch.object(McpSyncService, "build_merged_config", return_value=new_agented):
            result = McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        content = json.loads((tmp_path / ".mcp.json").read_text())
        assert "user-custom" in content
        assert "old-agented" not in content
        assert "new-srv" in content

    def test_backup_created_on_overwrite(self, tmp_path):
        """A .bak file is created when overwriting an existing .mcp.json."""
        original = {"existing": {"command": "test"}}
        (tmp_path / ".mcp.json").write_text(json.dumps(original))

        with patch.object(McpSyncService, "build_merged_config", return_value={}):
            result = McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        backup = Path(result["backup"])
        assert backup.exists()
        assert json.loads(backup.read_text()) == original

    def test_corrupt_json_returns_error(self, tmp_path):
        """Corrupt .mcp.json returns error dict without crashing."""
        (tmp_path / ".mcp.json").write_text("{invalid json!!!")

        result = McpSyncService.sync_project("proj-1", str(tmp_path))
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_build_config_exception_returns_error(self, tmp_path):
        """Exception in build_merged_config is caught and returned as error."""
        with patch.object(
            McpSyncService, "build_merged_config", side_effect=RuntimeError("DB down")
        ):
            result = McpSyncService.sync_project("proj-1", str(tmp_path))

        assert "error" in result
        assert "DB down" in result["error"]

    def test_permission_error_returns_error(self, tmp_path):
        """PermissionError during write is caught and returned as error."""
        with patch.object(McpSyncService, "build_merged_config", return_value={}):
            with patch("tempfile.mkstemp", side_effect=PermissionError("denied")):
                result = McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        assert "error" in result
        assert "Permission denied" in result["error"]

    def test_atomic_write_cleans_up_temp_on_failure(self, tmp_path):
        """If os.replace fails, the temp file is cleaned up."""
        with patch.object(McpSyncService, "build_merged_config", return_value={}):
            with patch("os.replace", side_effect=OSError("replace failed")):
                with pytest.raises(OSError, match="replace failed"):
                    McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        # No leftover temp files
        tmp_files = list(tmp_path.glob("*.mcp.json.tmp"))
        assert tmp_files == []

    def test_file_ends_with_newline(self, tmp_path):
        """Written .mcp.json ends with a trailing newline."""
        agented = {"srv": {"_agented_managed": True, "command": "npx", "args": []}}

        with patch.object(McpSyncService, "build_merged_config", return_value=agented):
            McpSyncService.sync_project("proj-1", str(tmp_path), dry_run=False)

        raw = (tmp_path / ".mcp.json").read_text()
        assert raw.endswith("\n")


# ---------------------------------------------------------------------------
# _compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    """Tests for the internal _compute_diff method."""

    def test_identical_dicts_empty_diff(self):
        """Identical configs produce empty diff string."""
        data = {"a": 1}
        assert McpSyncService._compute_diff(data, data) == ""

    def test_different_dicts_nonempty_diff(self):
        """Changed configs produce unified diff with from/to headers."""
        old = {"server": {"command": "old"}}
        new = {"server": {"command": "new"}}
        diff = McpSyncService._compute_diff(old, new)

        assert "current .mcp.json" in diff
        assert "after sync" in diff
        assert "-" in diff and "+" in diff


# ---------------------------------------------------------------------------
# validate_project_path
# ---------------------------------------------------------------------------


class TestValidateProjectPath:
    """Tests for validate_project_path."""

    def test_valid_directory(self, tmp_path):
        ok, reason = McpSyncService.validate_project_path(str(tmp_path))
        assert ok is True
        assert reason == ""

    def test_nonexistent_path(self):
        ok, reason = McpSyncService.validate_project_path("/no/such/path/xyz")
        assert ok is False
        assert "does not exist" in reason

    def test_file_not_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        ok, reason = McpSyncService.validate_project_path(str(f))
        assert ok is False
        assert "not a directory" in reason

    def test_no_write_permission(self, tmp_path):
        """Directory without write permission fails validation."""
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        ro_dir.chmod(0o444)
        try:
            ok, reason = McpSyncService.validate_project_path(str(ro_dir))
            assert ok is False
            assert "No write permission" in reason
        finally:
            ro_dir.chmod(0o755)  # restore for cleanup
