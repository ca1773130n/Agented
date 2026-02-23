"""Unit tests for McpSyncService -- MCP config sync to Claude Code .mcp.json format."""

import json
from pathlib import Path
from unittest.mock import patch

from app.services.mcp_sync_service import McpSyncService

# =============================================================================
# Test 1: transform_to_claude for stdio server
# =============================================================================


def test_transform_stdio_server():
    """Stdio server produces command + args + _agented_managed, empty env omitted."""
    server = {
        "name": "ctx7",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@upstash/context7-mcp"]',
        "env_json": "{}",
    }
    result = McpSyncService.transform_to_claude(server)

    assert result["_agented_managed"] is True
    assert result["command"] == "npx"
    assert result["args"] == ["-y", "@upstash/context7-mcp"]
    assert "env" not in result  # empty dict omitted


# =============================================================================
# Test 2: transform_to_claude for http server
# =============================================================================


def test_transform_http_server():
    """HTTP server produces type + url + _agented_managed, empty headers omitted."""
    server = {
        "name": "github",
        "server_type": "http",
        "url": "https://api.github.com/mcp/",
        "headers_json": "{}",
    }
    result = McpSyncService.transform_to_claude(server)

    assert result["_agented_managed"] is True
    assert result["type"] == "http"
    assert result["url"] == "https://api.github.com/mcp/"
    assert "headers" not in result  # empty headers omitted


# =============================================================================
# Test 3: transform_to_claude with env overrides
# =============================================================================


def test_transform_env_overrides():
    """Env overrides merge with base env, overrides win."""
    server = {
        "name": "test",
        "server_type": "stdio",
        "command": "npx",
        "args": "[]",
        "env_json": '{"KEY": "${DEFAULT}", "OTHER": "keep"}',
    }
    env_overrides = '{"KEY": "${CUSTOM}"}'
    result = McpSyncService.transform_to_claude(server, env_overrides)

    assert result["env"]["KEY"] == "${CUSTOM}"
    assert result["env"]["OTHER"] == "keep"


# =============================================================================
# Test 4: sync_project dry_run returns diff without writing
# =============================================================================


def test_sync_project_dry_run(tmp_path):
    """Dry-run returns diff and does NOT modify the existing .mcp.json file."""
    # Write existing .mcp.json with a user entry
    existing = {"my-custom": {"command": "python", "args": ["-m", "my_server"]}}
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text(json.dumps(existing, indent=2))
    original_content = mcp_file.read_text()

    # Mock get_project_mcp_servers to return one enabled server
    mock_servers = [
        {
            "server_name": "ctx7",
            "name": "ctx7",
            "server_type": "stdio",
            "command": "npx",
            "args": '["-y", "@upstash/context7-mcp"]',
            "env_json": "{}",
            "enabled": 1,
            "config_override": None,
        }
    ]

    with patch("app.services.mcp_sync_service.McpSyncService.build_merged_config") as mock_build:
        mock_build.return_value = {"ctx7": McpSyncService.transform_to_claude(mock_servers[0])}
        result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=True)

    assert "diff" in result
    assert "would_write" in result
    assert result["servers_count"] == 1
    # File must be UNCHANGED
    assert mcp_file.read_text() == original_content


# =============================================================================
# Test 5: sync_project writes .mcp.json with Agented entries
# =============================================================================


def test_sync_project_writes_mcp_json(tmp_path):
    """Live sync creates .mcp.json with Agented-managed entries."""
    mock_servers_data = {
        "ctx7": {
            "_agented_managed": True,
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
        },
        "playwright": {
            "_agented_managed": True,
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
        },
    }

    with patch("app.services.mcp_sync_service.McpSyncService.build_merged_config") as mock_build:
        mock_build.return_value = mock_servers_data
        result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=False)

    assert "written" in result
    assert result["servers"] == 2

    # Verify file exists and is valid JSON
    mcp_file = tmp_path / ".mcp.json"
    assert mcp_file.exists()
    content = json.loads(mcp_file.read_text())
    assert content["ctx7"]["_agented_managed"] is True
    assert content["playwright"]["_agented_managed"] is True


# =============================================================================
# Test 6: sync_project preserves non-Agented entries
# =============================================================================


def test_sync_project_preserves_non_agented_entries(tmp_path):
    """Non-Agented entries (without _agented_managed) survive sync. Old Agented entries replaced."""
    existing = {
        "my-custom": {"command": "python", "args": ["-m", "my_server"]},
        "agented-old": {"_agented_managed": True, "command": "old"},
    }
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text(json.dumps(existing, indent=2))

    new_agented_entry = {
        "ctx7": {
            "_agented_managed": True,
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
        }
    }

    with patch("app.services.mcp_sync_service.McpSyncService.build_merged_config") as mock_build:
        mock_build.return_value = new_agented_entry
        result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=False)

    assert "written" in result
    content = json.loads(mcp_file.read_text())

    # my-custom preserved exactly
    assert content["my-custom"] == {"command": "python", "args": ["-m", "my_server"]}
    # agented-old removed (was _agented_managed, not in new build)
    assert "agented-old" not in content
    # new Agented entry present
    assert content["ctx7"]["_agented_managed"] is True


# =============================================================================
# Test 7: sync_project creates backup
# =============================================================================


def test_sync_project_creates_backup(tmp_path):
    """Backup .mcp.json.bak is created when overwriting existing file."""
    existing = {"existing": {"command": "test"}}
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text(json.dumps(existing, indent=2))

    with patch("app.services.mcp_sync_service.McpSyncService.build_merged_config") as mock_build:
        mock_build.return_value = {"new-server": {"_agented_managed": True, "command": "npx"}}
        result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=False)

    assert result.get("backup") is not None
    backup_file = Path(result["backup"])
    assert backup_file.exists()
    # Backup contains original content
    backup_content = json.loads(backup_file.read_text())
    assert backup_content == existing


# =============================================================================
# Test 8: disabled servers excluded from sync
# =============================================================================


def test_disabled_servers_excluded(tmp_path):
    """Servers with enabled=0 are not included in sync output."""
    mock_servers = [
        {
            "server_name": "disabled-server",
            "name": "disabled-server",
            "server_type": "stdio",
            "command": "npx",
            "args": "[]",
            "env_json": "{}",
            "enabled": 0,
            "config_override": None,
        }
    ]

    with patch("app.db.get_project_mcp_servers", return_value=mock_servers):
        result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=False)

    assert "written" in result
    assert result["servers"] == 0

    mcp_file = tmp_path / ".mcp.json"
    content = json.loads(mcp_file.read_text())
    assert "disabled-server" not in content


# =============================================================================
# Additional edge case tests
# =============================================================================


def test_transform_sse_server():
    """SSE server uses type='sse' and url."""
    server = {
        "name": "custom-sse",
        "server_type": "sse",
        "url": "http://localhost:8080/sse",
        "headers_json": '{"Authorization": "Bearer ${TOKEN}"}',
    }
    result = McpSyncService.transform_to_claude(server)

    assert result["type"] == "sse"
    assert result["url"] == "http://localhost:8080/sse"
    assert result["headers"]["Authorization"] == "Bearer ${TOKEN}"


def test_sync_project_handles_corrupt_json(tmp_path):
    """Corrupt existing .mcp.json returns error instead of crashing."""
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text("not valid json {{{")

    result = McpSyncService.sync_project("proj-abc", str(tmp_path), dry_run=False)
    assert "error" in result
    assert "Invalid JSON" in result["error"]


def test_validate_project_path_valid(tmp_path):
    """Valid directory passes validation."""
    ok, reason = McpSyncService.validate_project_path(str(tmp_path))
    assert ok is True
    assert reason == ""


def test_validate_project_path_missing():
    """Non-existent path fails validation."""
    ok, reason = McpSyncService.validate_project_path("/nonexistent/path/12345")
    assert ok is False
    assert "does not exist" in reason


def test_validate_project_path_not_dir(tmp_path):
    """Path that is a file (not directory) fails validation."""
    f = tmp_path / "somefile.txt"
    f.write_text("hello")
    ok, reason = McpSyncService.validate_project_path(str(f))
    assert ok is False
    assert "not a directory" in reason


def test_compute_diff_no_changes():
    """Identical dicts produce empty diff."""
    data = {"foo": {"command": "bar"}}
    diff = McpSyncService._compute_diff(data, data)
    assert diff == ""


def test_compute_diff_with_changes():
    """Different dicts produce non-empty diff."""
    old = {"foo": {"command": "bar"}}
    new = {"foo": {"command": "baz"}}
    diff = McpSyncService._compute_diff(old, new)
    assert len(diff) > 0
    assert "bar" in diff
    assert "baz" in diff


def test_transform_stdio_with_none_args():
    """Server with None/missing args defaults to empty list."""
    server = {
        "name": "test",
        "server_type": "stdio",
        "command": "npx",
        "args": None,
        "env_json": None,
    }
    result = McpSyncService.transform_to_claude(server)
    assert result["args"] == []
    assert "env" not in result
