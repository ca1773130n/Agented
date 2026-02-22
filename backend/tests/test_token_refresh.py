"""Tests for CLIProxyManager token refresh functionality."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.cliproxy_manager import CLIProxyManager


class TestRefreshExpiredTokens:
    """Tests for refresh_expired_tokens orchestrator."""

    @patch.object(CLIProxyManager, "list_accounts", return_value=[])
    def test_no_accounts_returns_empty(self, mock_list):
        result = CLIProxyManager.refresh_expired_tokens()
        assert result == {"refreshed": [], "skipped": [], "failed": []}

    @patch.object(CLIProxyManager, "list_accounts")
    def test_skips_disabled_accounts(self, mock_list):
        mock_list.return_value = [
            {
                "email": "disabled@example.com",
                "disabled": True,
                "expired": "2020-01-01T00:00:00Z",
                "file": "claude-disabled.json",
            }
        ]
        result = CLIProxyManager.refresh_expired_tokens()
        assert "disabled@example.com" in result["skipped"]
        assert result["refreshed"] == []
        assert result["failed"] == []

    @patch.object(CLIProxyManager, "list_accounts")
    def test_skips_not_expired(self, mock_list):
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        mock_list.return_value = [
            {
                "email": "valid@example.com",
                "disabled": False,
                "expired": future,
                "file": "claude-valid.json",
            }
        ]
        result = CLIProxyManager.refresh_expired_tokens()
        assert "valid@example.com" in result["skipped"]
        assert result["refreshed"] == []
        assert result["failed"] == []

    @patch.object(CLIProxyManager, "_snapshot_cred_expiries")
    @patch.object(CLIProxyManager, "_run_oauth_flow", return_value=True)
    @patch.object(CLIProxyManager, "_find_chrome_profiles_with_session")
    @patch.object(CLIProxyManager, "list_accounts")
    def test_refreshes_expired_token(self, mock_list, mock_profiles, mock_oauth, mock_snapshot):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
        mock_list.return_value = [
            {
                "email": "expired@example.com",
                "disabled": False,
                "expired": past,
                "file": "claude-expired.json",
            }
        ]
        mock_profiles.return_value = [Path("/fake/Profile 1")]
        # First snapshot (before), then snapshot (after) showing updated expiry
        mock_snapshot.side_effect = [
            {"expired@example.com": past},
            {"expired@example.com": future},
        ]

        result = CLIProxyManager.refresh_expired_tokens()
        assert "expired@example.com" in result["refreshed"]
        assert result["failed"] == []
        mock_oauth.assert_called_once()

    @patch.object(CLIProxyManager, "_snapshot_cred_expiries")
    @patch.object(
        CLIProxyManager,
        "_run_oauth_flow",
        side_effect=RuntimeError("browser crash"),
    )
    @patch.object(CLIProxyManager, "_find_chrome_profiles_with_session")
    @patch.object(CLIProxyManager, "list_accounts")
    def test_handles_refresh_exception(self, mock_list, mock_profiles, mock_oauth, mock_snapshot):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_list.return_value = [
            {
                "email": "crash@example.com",
                "disabled": False,
                "expired": past,
                "file": "claude-crash.json",
            }
        ]
        mock_profiles.return_value = [Path("/fake/Profile 1")]
        mock_snapshot.return_value = {"crash@example.com": past}

        result = CLIProxyManager.refresh_expired_tokens()
        assert "crash@example.com" in result["failed"]
        assert result["refreshed"] == []


class TestRunOauthFlow:
    """Tests for _run_oauth_flow."""

    @patch("subprocess.Popen", side_effect=FileNotFoundError)
    def test_binary_not_found_returns_false(self, mock_popen):
        result = CLIProxyManager._run_oauth_flow(Path("/fake/profile"), timeout=10)
        assert result is False

    @patch("subprocess.Popen")
    def test_no_oauth_url_returns_false(self, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = 0  # Process exits immediately
        proc.stdout.readline.return_value = ""
        mock_popen.return_value = proc

        result = CLIProxyManager._run_oauth_flow(Path("/fake/profile"), timeout=5)
        assert result is False
        proc.kill.assert_called()

    @patch.object(CLIProxyManager, "_run_playwright_oauth", return_value=False)
    @patch("subprocess.Popen")
    def test_playwright_failure_returns_false(self, mock_popen, mock_oauth):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdout.readline.side_effect = [
            "Starting OAuth flow...\n",
            "Open this URL: https://claude.ai/oauth?redirect_uri=http%3A%2F%2Flocalhost%3A9876%2Fcallback\n",
        ]
        mock_popen.return_value = proc

        result = CLIProxyManager._run_oauth_flow(Path("/fake/profile"), timeout=10)
        assert result is False
        mock_oauth.assert_called_once()


class TestRunPlaywrightOauth:
    """Tests for _run_playwright_oauth."""

    def test_playwright_import_error_returns_false(self):
        """When playwright is not importable, _run_playwright_oauth returns False."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "playwright.sync_api":
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = CLIProxyManager._run_playwright_oauth(
                "https://claude.ai/oauth", 9876, timeout=5
            )
            assert result is False
