"""Tests for ProviderUsageClient and CredentialResolver."""

import json
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.provider_usage_client import (
    CredentialResolver,
    ProviderUsageClient,
    _http_get,
    _http_post,
    _read_json_field,
    _read_json_file,
    _refresh_google_token,
)


# ---------------------------------------------------------------------------
# _http_get / _http_post helpers
# ---------------------------------------------------------------------------


class TestHttpGet:
    """Tests for the _http_get helper."""

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b'{"ok": true}'
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = _http_get("https://example.com/api", {"Authorization": "Bearer tok"})
        assert result == {"ok": True}

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_http_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", {}, None
        )
        assert _http_get("https://example.com", {}) is None

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_network_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        assert _http_get("https://example.com", {}) is None

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_invalid_json_returns_none(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        assert _http_get("https://example.com", {}) is None


class TestHttpPost:
    """Tests for the _http_post helper."""

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b'{"result": "ok"}'
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = _http_post("https://example.com/api", {}, b'{"data": 1}')
        assert result == {"result": "ok"}

    @patch("app.services.provider_usage_client.urllib.request.urlopen")
    def test_http_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com", 500, "Server Error", {}, None
        )
        assert _http_post("https://example.com", {}, b"{}") is None


# ---------------------------------------------------------------------------
# _read_json_file / _read_json_field
# ---------------------------------------------------------------------------


class TestReadJsonHelpers:
    """Tests for JSON file reading helpers."""

    def test_read_json_file_valid(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        assert _read_json_file(f) == {"key": "value"}

    def test_read_json_file_missing(self, tmp_path):
        assert _read_json_file(tmp_path / "missing.json") is None

    def test_read_json_file_invalid(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not valid json")
        assert _read_json_file(f) is None

    def test_read_json_field_nested(self, tmp_path):
        f = tmp_path / "nested.json"
        f.write_text('{"a": {"b": "deep"}}')
        assert _read_json_field(f, ["a", "b"]) == "deep"

    def test_read_json_field_missing_key(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}')
        assert _read_json_field(f, ["x", "y"]) is None


# ---------------------------------------------------------------------------
# CredentialResolver
# ---------------------------------------------------------------------------


class TestCredentialResolverClaude:
    """Tests for CredentialResolver.get_claude_token."""

    def test_default_account_from_file(self, tmp_path, monkeypatch):
        """Default account reads from ~/.claude/.credentials.json."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-abc"}}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Force non-Darwin to skip Keychain
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")

        token = CredentialResolver.get_claude_token({})
        assert token == "tok-abc"

    def test_custom_config_path_from_file(self, tmp_path, monkeypatch):
        """Non-default account reads from config_path/.credentials.json."""
        config_dir = tmp_path / "custom-config"
        config_dir.mkdir()
        cred_file = config_dir / ".credentials.json"
        cred_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-custom"}}))

        # Ensure it's recognized as non-default
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "other-home")
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")

        token = CredentialResolver.get_claude_token({"config_path": str(config_dir)})
        assert token == "tok-custom"

    def test_no_credentials_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")
        assert CredentialResolver.get_claude_token({}) is None


class TestCredentialResolverCodex:
    """Tests for CredentialResolver.get_codex_token."""

    def test_default_auth(self, tmp_path, monkeypatch):
        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir()
        auth_file = auth_dir / "auth.json"
        auth_file.write_text(
            json.dumps({"tokens": {"access_token": "codex-tok", "account_id": "acct-1"}})
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        token, acct_id = CredentialResolver.get_codex_token({})
        assert token == "codex-tok"
        assert acct_id == "acct-1"

    def test_custom_config_path(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "custom-codex"
        config_dir.mkdir()
        (config_dir / "auth.json").write_text(
            json.dumps({"tokens": {"access_token": "custom-tok", "account_id": "acct-2"}})
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        token, acct_id = CredentialResolver.get_codex_token({"config_path": str(config_dir)})
        assert token == "custom-tok"
        assert acct_id == "acct-2"

    def test_no_auth_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        token, acct_id = CredentialResolver.get_codex_token({})
        assert token is None
        assert acct_id is None


class TestCredentialResolverGemini:
    """Tests for CredentialResolver.get_gemini_token."""

    def test_valid_non_expired_token(self, tmp_path, monkeypatch):
        cred_dir = tmp_path / ".gemini"
        cred_dir.mkdir()
        future_ms = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp() * 1000)
        cred_file = cred_dir / "oauth_creds.json"
        cred_file.write_text(
            json.dumps(
                {
                    "access_token": "gem-tok",
                    "refresh_token": "ref-tok",
                    "expiry_date": str(future_ms),
                }
            )
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")

        token = CredentialResolver.get_gemini_token({})
        assert token == "gem-tok"

    def test_expired_token_refreshes(self, tmp_path, monkeypatch):
        cred_dir = tmp_path / ".gemini"
        cred_dir.mkdir()
        past_ms = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp() * 1000)
        cred_file = cred_dir / "oauth_creds.json"
        cred_file.write_text(
            json.dumps(
                {
                    "access_token": "old-tok",
                    "refresh_token": "ref-tok",
                    "expiry_date": str(past_ms),
                }
            )
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")

        with patch(
            "app.services.provider_usage_client._refresh_google_token", return_value="new-tok"
        ):
            token = CredentialResolver.get_gemini_token({})
        assert token == "new-tok"

    def test_no_credentials_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")
        assert CredentialResolver.get_gemini_token({}) is None


class TestTokenFingerprint:
    """Tests for CredentialResolver.get_token_fingerprint."""

    def test_returns_fingerprint_for_claude(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")
        cred_file = tmp_path / ".claude" / ".credentials.json"
        cred_file.parent.mkdir(parents=True)
        cred_file.write_text(json.dumps({"claudeAiOauth": {"accessToken": "fingerprint-tok"}}))

        fp = CredentialResolver.get_token_fingerprint({}, "claude")
        assert fp is not None
        assert len(fp) == 12

    def test_returns_none_when_no_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("app.services.provider_usage_client.platform.system", lambda: "Linux")
        assert CredentialResolver.get_token_fingerprint({}, "claude") is None


# ---------------------------------------------------------------------------
# _refresh_google_token
# ---------------------------------------------------------------------------


class TestRefreshGoogleToken:
    """Tests for _refresh_google_token."""

    @patch("app.services.provider_usage_client._http_post")
    def test_success(self, mock_post):
        mock_post.return_value = {"access_token": "refreshed-tok"}
        result = _refresh_google_token("ref", "cid", "csecret")
        assert result == "refreshed-tok"

    @patch("app.services.provider_usage_client._http_post")
    def test_failure_returns_none(self, mock_post):
        mock_post.return_value = None
        assert _refresh_google_token("ref", "cid", "csecret") is None


# ---------------------------------------------------------------------------
# ProviderUsageClient.fetch_usage dispatch
# ---------------------------------------------------------------------------


class TestFetchUsageDispatch:
    """Tests for ProviderUsageClient.fetch_usage dispatch logic."""

    def test_unknown_backend_returns_empty(self):
        assert ProviderUsageClient.fetch_usage({}, "unknown_backend") == []

    @patch.object(ProviderUsageClient, "_fetch_claude", return_value=[{"window_type": "five_hour"}])
    def test_dispatches_to_claude(self, mock_fetch):
        result = ProviderUsageClient.fetch_usage({"id": "a1"}, "claude")
        assert result == [{"window_type": "five_hour"}]
        mock_fetch.assert_called_once_with({"id": "a1"})

    @patch.object(ProviderUsageClient, "_fetch_codex", return_value=[])
    def test_dispatches_to_codex(self, mock_fetch):
        ProviderUsageClient.fetch_usage({"id": "a2"}, "codex")
        mock_fetch.assert_called_once()

    @patch.object(ProviderUsageClient, "_fetch_gemini", return_value=[])
    def test_dispatches_to_gemini(self, mock_fetch):
        ProviderUsageClient.fetch_usage({"id": "a3"}, "gemini")
        mock_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# ProviderUsageClient._fetch_claude
# ---------------------------------------------------------------------------


class TestFetchClaude:
    """Tests for ProviderUsageClient._fetch_claude."""

    @patch("app.services.provider_usage_client._http_get")
    @patch.object(CredentialResolver, "get_claude_token", return_value="tok-123")
    def test_parses_windows(self, mock_token, mock_get):
        mock_get.return_value = {
            "five_hour": {"utilization": 0.45, "resets_at": "2026-01-01T10:00:00Z"},
            "seven_day": {"utilization": 0.12, "resets_at": "2026-01-07T00:00:00Z"},
        }
        result = ProviderUsageClient._fetch_claude({"id": "a1"})
        assert len(result) == 2
        assert result[0]["window_type"] == "five_hour"
        assert result[0]["percentage"] == 0.5
        assert result[1]["window_type"] == "seven_day"
        assert result[1]["percentage"] == 0.1

    @patch.object(CredentialResolver, "get_claude_token", return_value=None)
    def test_no_token_returns_empty(self, mock_token):
        assert ProviderUsageClient._fetch_claude({"id": "a1"}) == []

    @patch("app.services.provider_usage_client._http_get", return_value=None)
    @patch.object(CredentialResolver, "get_claude_token", return_value="tok")
    def test_api_failure_returns_empty(self, mock_token, mock_get):
        assert ProviderUsageClient._fetch_claude({"id": "a1"}) == []


# ---------------------------------------------------------------------------
# ProviderUsageClient._fetch_gemini
# ---------------------------------------------------------------------------


class TestFetchGemini:
    """Tests for ProviderUsageClient._fetch_gemini."""

    @patch("app.services.provider_usage_client._http_post")
    @patch.object(CredentialResolver, "get_gemini_token", return_value="gem-tok")
    def test_parses_buckets_and_filters(self, mock_token, mock_post):
        mock_post.return_value = {
            "buckets": [
                {
                    "modelId": "gemini-3-pro-preview",
                    "remainingFraction": 0.7,
                    "resetTime": "2026-01-01T12:00:00Z",
                },
                {
                    "modelId": "gemini-2.0-flash",
                    "remainingFraction": 0.9,
                    "resetTime": "2026-01-01T12:00:00Z",
                },
                {
                    "modelId": "gemini-3-pro_vertex",
                    "remainingFraction": 0.5,
                },
            ]
        }
        result = ProviderUsageClient._fetch_gemini({"id": "a1"})
        # Should only include gemini-3-pro-preview (vertex and 2.0 filtered)
        assert len(result) == 1
        assert result[0]["window_type"] == "gemini-3-pro-preview"
        assert result[0]["percentage"] == 30.0
        assert result[0]["resets_at"] == "2026-01-01T12:00:00Z"

    @patch.object(CredentialResolver, "get_gemini_token", return_value=None)
    def test_no_token_returns_empty(self, mock_token):
        assert ProviderUsageClient._fetch_gemini({"id": "a1"}) == []


# ---------------------------------------------------------------------------
# ProviderUsageClient._fetch_codex (HTTP path only)
# ---------------------------------------------------------------------------


class TestFetchCodex:
    """Tests for ProviderUsageClient._fetch_codex HTTP path."""

    @patch("app.services.provider_usage_client._http_get")
    @patch.object(CredentialResolver, "get_codex_token", return_value=("codex-tok", "acct-1"))
    @patch.object(ProviderUsageClient, "_fetch_codex_via_pty", return_value=None)
    def test_http_fallback_parses_windows(self, mock_pty, mock_cred, mock_get):
        mock_get.return_value = {
            "rate_limit": {
                "primary_window": {"used_percent": 25.0, "reset_at": None},
            },
            "additional_rate_limits": [
                {
                    "limit_name": "GPT-5-Codex-Spark",
                    "rate_limit": {
                        "primary_window": {"used_percent": 10.0, "reset_at": None},
                    },
                }
            ],
        }
        result = ProviderUsageClient._fetch_codex({"id": "a1"})
        assert len(result) == 2
        # Base model derived from first additional name: "GPT-5-Codex"
        assert result[0]["window_type"] == "GPT-5-Codex_primary_window"
        assert result[0]["percentage"] == 25.0

    @patch.object(ProviderUsageClient, "_fetch_codex_via_pty", return_value=None)
    @patch.object(CredentialResolver, "get_codex_token", return_value=(None, None))
    def test_no_token_returns_empty(self, mock_cred, mock_pty):
        assert ProviderUsageClient._fetch_codex({"id": "a1"}) == []
