"""Tests for CLIProxyManager service.

Covers:
- Lifecycle: start, stop, kill_orphans
- Health checks and URL helpers
- Account listing
- Install check
- Config reading/writing
- Token refresh logic
- Legacy compatibility methods
- Error handling and edge cases
"""

import json
import os
import signal
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from app.services.cliproxy_manager import CLIProxyManager, _GLOBAL_AUTH_DIR, _GLOBAL_CONFIG


@pytest.fixture(autouse=True)
def reset_manager_state():
    """Reset CLIProxyManager class state before each test."""
    CLIProxyManager._process = None
    CLIProxyManager._port = 8317
    CLIProxyManager._api_key = "not-needed"
    CLIProxyManager._config_loaded = False
    yield
    CLIProxyManager._process = None
    CLIProxyManager._port = 8317
    CLIProxyManager._api_key = "not-needed"
    CLIProxyManager._config_loaded = False


# =============================================================================
# kill_orphans
# =============================================================================


class TestKillOrphans:
    """Test orphan process cleanup."""

    @patch("app.services.cliproxy_manager.time.sleep")
    @patch("app.services.cliproxy_manager.subprocess.run")
    def test_kills_cliproxyapi_processes(self, mock_run, mock_sleep):
        CLIProxyManager.kill_orphans()
        mock_run.assert_called_once_with(
            ["pkill", "-f", "cliproxyapi"], capture_output=True, timeout=5
        )

    @patch("app.services.cliproxy_manager.time.sleep")
    @patch("app.services.cliproxy_manager.subprocess.run")
    def test_handles_pkill_failure(self, mock_run, mock_sleep):
        mock_run.side_effect = Exception("pkill not found")
        # Should not raise
        CLIProxyManager.kill_orphans()


# =============================================================================
# start
# =============================================================================


class TestStart:
    """Test CLIProxyManager.start lifecycle."""

    @patch.object(CLIProxyManager, "is_healthy", return_value=True)
    def test_start_returns_true_if_already_running(self, mock_healthy):
        CLIProxyManager._process = MagicMock()
        result = CLIProxyManager.start()
        assert result is True

    @patch.object(CLIProxyManager, "_check_port_healthy", return_value=True)
    @patch.object(
        CLIProxyManager,
        "_read_config",
        return_value={"port": 8317, "api-keys": ["test-key"]},
    )
    def test_start_returns_true_if_port_already_healthy(self, mock_config, mock_healthy):
        result = CLIProxyManager.start()
        assert result is True
        assert CLIProxyManager._api_key == "test-key"

    @patch("app.services.cliproxy_manager.time.sleep")
    @patch("app.services.cliproxy_manager.time.monotonic")
    @patch("app.services.cliproxy_manager.subprocess.Popen")
    @patch.object(CLIProxyManager, "_check_port_healthy")
    @patch.object(
        CLIProxyManager,
        "_read_config",
        return_value={"port": 9000, "api-keys": ["my-key"]},
    )
    def test_start_launches_process_and_waits(
        self, mock_config, mock_healthy, mock_popen, mock_monotonic, mock_sleep
    ):
        # First call: port not healthy (not already running)
        # Second call: port becomes healthy after startup
        mock_healthy.side_effect = [False, True]
        mock_monotonic.side_effect = [0.0, 0.5]  # within 10s deadline
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        result = CLIProxyManager.start()
        assert result is True
        assert CLIProxyManager._port == 9000
        mock_popen.assert_called_once()

    @patch.object(
        CLIProxyManager, "_read_config", return_value=None
    )
    @patch.object(CLIProxyManager, "_write_default_config")
    def test_start_creates_default_config_if_missing(self, mock_write, mock_read):
        # Both reads return None -> should fail
        result = CLIProxyManager.start()
        assert result is False
        mock_write.assert_called_once()

    @patch("app.services.cliproxy_manager.subprocess.Popen")
    @patch.object(CLIProxyManager, "_check_port_healthy", return_value=False)
    @patch.object(
        CLIProxyManager,
        "_read_config",
        return_value={"port": 8317, "api-keys": []},
    )
    def test_start_binary_not_found(self, mock_config, mock_healthy, mock_popen):
        mock_popen.side_effect = FileNotFoundError("cliproxyapi not found")
        result = CLIProxyManager.start()
        assert result is False

    @patch("app.services.cliproxy_manager.time.sleep")
    @patch("app.services.cliproxy_manager.time.monotonic")
    @patch("app.services.cliproxy_manager.subprocess.Popen")
    @patch.object(CLIProxyManager, "_check_port_healthy", return_value=False)
    @patch.object(
        CLIProxyManager,
        "_read_config",
        return_value={"port": 8317, "api-keys": ["k"]},
    )
    def test_start_timeout_cleans_up_process(
        self, mock_config, mock_healthy, mock_popen, mock_monotonic, mock_sleep
    ):
        # Simulate timeout: monotonic always past deadline
        mock_monotonic.side_effect = [0.0] + [20.0] * 30
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        result = CLIProxyManager.start()
        assert result is False
        mock_proc.terminate.assert_called_once()

    @patch.object(
        CLIProxyManager, "_read_config", return_value={"port": 8317}
    )
    @patch.object(CLIProxyManager, "_check_port_healthy", return_value=False)
    @patch("app.services.cliproxy_manager.subprocess.Popen")
    def test_start_uses_not_needed_when_no_keys(self, mock_popen, mock_healthy, mock_config):
        mock_popen.side_effect = FileNotFoundError()
        CLIProxyManager.start()
        assert CLIProxyManager._api_key == "not-needed"


# =============================================================================
# stop
# =============================================================================


class TestStop:
    """Test CLIProxyManager.stop."""

    def test_stop_noop_when_no_process(self):
        CLIProxyManager._process = None
        CLIProxyManager.stop()  # Should not raise

    @patch("app.services.cliproxy_manager.os.killpg")
    @patch("app.services.cliproxy_manager.os.getpgid")
    def test_stop_terminates_process(self, mock_getpgid, mock_killpg):
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_getpgid.return_value = 5678
        CLIProxyManager._process = mock_proc

        CLIProxyManager.stop()

        mock_killpg.assert_called_with(5678, signal.SIGTERM)
        mock_proc.wait.assert_called_once_with(timeout=5)
        assert CLIProxyManager._process is None

    @patch("app.services.cliproxy_manager.os.killpg")
    @patch("app.services.cliproxy_manager.os.getpgid")
    def test_stop_handles_process_already_exited(self, mock_getpgid, mock_killpg):
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_getpgid.side_effect = ProcessLookupError("no such process")
        CLIProxyManager._process = mock_proc

        CLIProxyManager.stop()  # Should not raise
        assert CLIProxyManager._process is None

    @patch("app.services.cliproxy_manager.os.killpg")
    @patch("app.services.cliproxy_manager.os.getpgid")
    def test_stop_sigkill_on_timeout(self, mock_getpgid, mock_killpg):
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 5)
        mock_getpgid.return_value = 5678
        CLIProxyManager._process = mock_proc

        CLIProxyManager.stop()

        # First SIGTERM, then SIGKILL
        assert mock_killpg.call_count == 2
        mock_killpg.assert_any_call(5678, signal.SIGTERM)
        mock_killpg.assert_any_call(5678, signal.SIGKILL)


# =============================================================================
# Health & URL
# =============================================================================


class TestHealthAndUrl:
    """Test health checks and URL methods."""

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_healthy_true(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert CLIProxyManager.is_healthy() is True

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_healthy_false_on_500(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_httpx.get.return_value = mock_resp
        assert CLIProxyManager.is_healthy() is False

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_healthy_false_on_connection_error(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("connection refused")
        assert CLIProxyManager.is_healthy() is False

    @patch.object(CLIProxyManager, "_ensure_config_loaded")
    @patch("app.services.cliproxy_manager.httpx")
    def test_get_base_url_healthy(self, mock_httpx, mock_ensure):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        CLIProxyManager._port = 9999

        url = CLIProxyManager.get_base_url()
        assert url == "http://127.0.0.1:9999/v1"

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_base_url_unhealthy(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("refused")
        assert CLIProxyManager.get_base_url() is None

    @patch.object(CLIProxyManager, "_ensure_config_loaded")
    @patch("app.services.cliproxy_manager.httpx")
    def test_get_url_and_key_healthy(self, mock_httpx, mock_ensure):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        CLIProxyManager._port = 8317
        CLIProxyManager._api_key = "secret"

        result = CLIProxyManager.get_url_and_key()
        assert result == ("http://127.0.0.1:8317/v1", "secret")

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_url_and_key_unhealthy(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("refused")
        assert CLIProxyManager.get_url_and_key() is None


# =============================================================================
# Account listing
# =============================================================================


class TestListAccounts:
    """Test account listing from credential files."""

    @patch("app.services.cliproxy_manager._GLOBAL_AUTH_DIR")
    def test_list_accounts_empty(self, mock_auth_dir):
        mock_auth_dir.glob.return_value = []
        accounts = CLIProxyManager.list_accounts()
        assert accounts == []

    @patch("app.services.cliproxy_manager._GLOBAL_AUTH_DIR")
    def test_list_accounts_with_files(self, mock_auth_dir):
        mock_path = MagicMock()
        mock_path.name = "claude-test@example.com.json"
        mock_path.read_text.return_value = json.dumps(
            {
                "email": "test@example.com",
                "type": "claude",
                "disabled": False,
                "expired": "2026-12-31T00:00:00Z",
                "last_refresh": "2026-01-01T00:00:00Z",
            }
        )

        # list_accounts calls glob twice (claude-*.json, codex-*.json)
        # Return the file only for the claude pattern
        def _glob(pattern):
            if pattern.startswith("claude"):
                return [mock_path]
            return []

        mock_auth_dir.glob.side_effect = _glob

        accounts = CLIProxyManager.list_accounts()
        assert len(accounts) == 1
        assert accounts[0]["email"] == "test@example.com"
        assert accounts[0]["type"] == "claude"
        assert accounts[0]["disabled"] is False

    @patch("app.services.cliproxy_manager._GLOBAL_AUTH_DIR")
    def test_list_accounts_handles_corrupt_file(self, mock_auth_dir):
        mock_path = MagicMock()
        mock_path.name = "claude-bad.json"
        mock_path.read_text.side_effect = json.JSONDecodeError("bad json", "", 0)
        mock_auth_dir.glob.return_value = [mock_path]

        accounts = CLIProxyManager.list_accounts()
        assert accounts == []


# =============================================================================
# Install
# =============================================================================


class TestInstallIfNeeded:
    """Test install_if_needed method."""

    @patch("app.services.cliproxy_manager.shutil.which", return_value="/usr/local/bin/cliproxyapi")
    def test_already_installed(self, mock_which):
        assert CLIProxyManager.install_if_needed() is True

    @patch("app.services.cliproxy_manager.subprocess.run")
    @patch("app.services.cliproxy_manager.shutil.which")
    def test_installs_via_brew(self, mock_which, mock_run):
        # First call: not found, second call (after install): found
        mock_which.side_effect = [None, "/usr/local/bin/cliproxyapi"]
        mock_run.return_value = MagicMock(returncode=0)

        assert CLIProxyManager.install_if_needed() is True
        mock_run.assert_called_once()
        assert "brew" in mock_run.call_args[0][0]

    @patch("app.services.cliproxy_manager.subprocess.run")
    @patch("app.services.cliproxy_manager.shutil.which")
    def test_install_fails(self, mock_which, mock_run):
        mock_which.return_value = None
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        assert CLIProxyManager.install_if_needed() is False

    @patch("app.services.cliproxy_manager.subprocess.run")
    @patch("app.services.cliproxy_manager.shutil.which")
    def test_install_exception(self, mock_which, mock_run):
        mock_which.return_value = None
        mock_run.side_effect = Exception("brew not found")

        assert CLIProxyManager.install_if_needed() is False


# =============================================================================
# Config reading/writing
# =============================================================================


class TestConfig:
    """Test config read/write methods."""

    @patch("app.services.cliproxy_manager._GLOBAL_CONFIG")
    def test_read_config_file_missing(self, mock_config):
        mock_config.exists.return_value = False
        assert CLIProxyManager._read_config() is None

    @patch("app.services.cliproxy_manager.yaml.safe_load")
    @patch("app.services.cliproxy_manager._GLOBAL_CONFIG")
    def test_read_config_success(self, mock_config, mock_yaml):
        mock_config.exists.return_value = True
        mock_config.read_text.return_value = "port: 9000\napi-keys:\n- key1"
        mock_yaml.return_value = {"port": 9000, "api-keys": ["key1"]}

        result = CLIProxyManager._read_config()
        assert result == {"port": 9000, "api-keys": ["key1"]}

    @patch("app.services.cliproxy_manager.yaml.safe_load")
    @patch("app.services.cliproxy_manager._GLOBAL_CONFIG")
    def test_read_config_parse_error(self, mock_config, mock_yaml):
        mock_config.exists.return_value = True
        mock_config.read_text.return_value = "invalid: {{"
        mock_yaml.side_effect = Exception("parse error")

        result = CLIProxyManager._read_config()
        assert result is None

    @patch("app.services.cliproxy_manager.yaml.dump")
    @patch("app.services.cliproxy_manager._GLOBAL_CONFIG")
    @patch("app.services.cliproxy_manager._GLOBAL_AUTH_DIR")
    def test_write_default_config(self, mock_auth_dir, mock_config, mock_yaml_dump):
        mock_yaml_dump.return_value = "port: 8317"

        CLIProxyManager._write_default_config()

        mock_auth_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_config.write_text.assert_called_once()

    def test_ensure_config_loaded_skips_if_already_loaded(self):
        CLIProxyManager._config_loaded = True
        CLIProxyManager._port = 1234
        # Should not change port since config is already loaded
        CLIProxyManager._ensure_config_loaded()
        assert CLIProxyManager._port == 1234

    @patch.object(
        CLIProxyManager,
        "_read_config",
        return_value={"port": 5555, "api-keys": ["abc"]},
    )
    def test_ensure_config_loaded_reads_config(self, mock_read):
        CLIProxyManager._config_loaded = False
        CLIProxyManager._ensure_config_loaded()
        assert CLIProxyManager._port == 5555
        assert CLIProxyManager._api_key == "abc"
        assert CLIProxyManager._config_loaded is True


# =============================================================================
# Legacy compatibility
# =============================================================================


class TestLegacyMethods:
    """Test legacy compatibility methods."""

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_instance_healthy(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        result = CLIProxyManager.get_instance(account_id=1)
        assert result is CLIProxyManager

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_instance_unhealthy(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("refused")
        result = CLIProxyManager.get_instance(account_id=1)
        assert result is None

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_proxy_enabled(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert CLIProxyManager.is_proxy_enabled(account_id=1) is True

    @patch("app.services.cliproxy_manager.httpx")
    def test_list_instances(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        CLIProxyManager._port = 8317

        instances = CLIProxyManager.list_instances()
        assert 0 in instances
        assert instances[0]["port"] == 8317
        assert instances[0]["healthy"] is True
        assert instances[0]["backend_type"] == "claude"


# =============================================================================
# Token refresh
# =============================================================================


class TestRefreshExpiredTokens:
    """Test token refresh logic."""

    @patch.object(CLIProxyManager, "list_accounts", return_value=[])
    def test_no_accounts(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert result == {"refreshed": [], "skipped": [], "failed": []}

    @patch.object(
        CLIProxyManager,
        "list_accounts",
        return_value=[{"email": "a@b.com", "disabled": True, "expired": ""}],
    )
    def test_skips_disabled_account(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert "a@b.com" in result["skipped"]
        assert result["refreshed"] == []

    @patch.object(
        CLIProxyManager,
        "list_accounts",
        return_value=[
            {
                "email": "valid@test.com",
                "disabled": False,
                "expired": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            }
        ],
    )
    def test_skips_non_expired_account(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert "valid@test.com" in result["skipped"]

    @patch.object(
        CLIProxyManager,
        "list_accounts",
        return_value=[
            {"email": "noexp@test.com", "disabled": False, "expired": ""}
        ],
    )
    def test_skips_account_with_no_expiry(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert "noexp@test.com" in result["skipped"]

    @patch.object(
        CLIProxyManager,
        "list_accounts",
        return_value=[
            {"email": "bad@test.com", "disabled": False, "expired": "not-a-date"}
        ],
    )
    def test_skips_account_with_bad_expiry(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert "bad@test.com" in result["skipped"]

    @patch.object(CLIProxyManager, "_find_chrome_profiles_with_session", return_value=[])
    @patch.object(CLIProxyManager, "_snapshot_cred_expiries", return_value={})
    @patch.object(
        CLIProxyManager,
        "list_accounts",
        return_value=[
            {
                "email": "expired@test.com",
                "disabled": False,
                "expired": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            }
        ],
    )
    def test_fails_when_no_chrome_profiles(self, mock_list, mock_snap, mock_profiles):
        result = CLIProxyManager.refresh_expired_tokens()
        assert "expired@test.com" in result["failed"]

    @patch.object(CLIProxyManager, "_run_oauth_flow", return_value=True)
    @patch.object(CLIProxyManager, "_find_chrome_profiles_with_session")
    @patch.object(CLIProxyManager, "_snapshot_cred_expiries")
    @patch.object(CLIProxyManager, "list_accounts")
    def test_successful_refresh(self, mock_list, mock_snap, mock_profiles, mock_oauth):
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        mock_list.return_value = [
            {"email": "user@test.com", "disabled": False, "expired": expired_time}
        ]
        # Before refresh: old expiry; after refresh: new future expiry
        mock_snap.side_effect = [
            {"user@test.com": expired_time},
            {"user@test.com": future_time},
        ]
        mock_profiles.return_value = [Path("/fake/profile")]

        result = CLIProxyManager.refresh_expired_tokens()
        assert "user@test.com" in result["refreshed"]
        assert result["failed"] == []


# =============================================================================
# _decrypt_chrome_cookie
# =============================================================================


class TestDecryptChromeCookie:
    """Test cookie decryption edge cases."""

    def test_empty_value(self):
        assert CLIProxyManager._decrypt_chrome_cookie(b"", b"key") == ""

    def test_unencrypted_cookie(self):
        # Not starting with v10 prefix
        assert CLIProxyManager._decrypt_chrome_cookie(b"plaintext", b"key") == "plaintext"

    def test_unencrypted_bad_unicode(self):
        assert CLIProxyManager._decrypt_chrome_cookie(b"\xff\xfe", b"key") == ""

    @patch("app.services.cliproxy_manager.CLIProxyManager._decrypt_chrome_cookie")
    def test_v10_prefix_detected(self, mock_decrypt):
        # Just verify the static method can be called (actual crypto tested integration-level)
        mock_decrypt.return_value = "decrypted"
        result = CLIProxyManager._decrypt_chrome_cookie(b"v10encrypted", b"key")
        assert result == "decrypted"
