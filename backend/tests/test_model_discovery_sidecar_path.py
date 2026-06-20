"""v0.7.9 / v0.7.11: sidecar-backed model discovery tests.

Updated for v0.7.11 to mirror the real flow: ask the sidecar for accounts
(GET /api/v1/backends/), pick one matching kind+auth_method, then ask for
its models. Auth uses Authorization: Bearer with the admin key from
user_roles (the sidecar's LazyFlaskKeyAuth shape).
"""

from unittest.mock import patch

import httpx

from app.services.model_discovery_service import ModelDiscoveryService


class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _RoutingClient:
    """httpx.Client mock that picks a response based on the URL path."""

    def __init__(self, routes, *, raise_on_match=None):
        # routes: dict[str_path_substring, _FakeResp]
        self._routes = routes
        self._raise = raise_on_match

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def get(self, url, *a, **kw):
        if self._raise is not None:
            raise self._raise
        for needle, resp in self._routes.items():
            if needle in url:
                return resp
        return _FakeResp(404, {"detail": "no mock for " + url})


def _admin_key_patch():
    class _Row:
        def __init__(self, key):
            self._key = key

        def __getitem__(self, k):
            return self._key

        def keys(self):
            return ("api_key",)

    class _Cur:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _Conn:
        def __init__(self, row):
            self._row = row

        def execute(self, *a, **kw):
            return _Cur(self._row)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    return patch(
        "app.db.connection.get_connection",
        lambda: _Conn(_Row("admin-key-xyz")),
    )


class TestSidecarDiscovery:
    def test_returns_models_on_200(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        list_body = {
            "items": [
                {"id": "acc-1", "kind": "claude", "status": "ready", "auth_method": "cli_browser"}
            ]
        }
        models_body = {"items": [{"id": "claude-opus-4-7"}, {"id": "claude-sonnet-4-7"}]}
        client = _RoutingClient(
            {
                "/backends/?": _FakeResp(200, list_body),
                "/acc-1/models": _FakeResp(200, models_body),
            }
        )
        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: client):
            result = ModelDiscoveryService._discover_via_sidecar(
                "claude",
                "cli_browser",
            )
        assert result == ["claude-opus-4-7", "claude-sonnet-4-7"]

    def test_returns_none_on_500(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        client = _RoutingClient(
            {
                "/backends/?": _FakeResp(
                    200, {"items": [{"id": "acc-1", "kind": "claude", "status": "ready"}]}
                ),
                "/acc-1/models": _FakeResp(500, {"detail": "boom"}),
            }
        )
        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: client):
            result = ModelDiscoveryService._discover_via_sidecar(
                "claude",
                "cli_browser",
            )
        assert result is None

    def test_returns_none_on_timeout(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        client = _RoutingClient({}, raise_on_match=httpx.TimeoutException("slow"))
        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: client):
            result = ModelDiscoveryService._discover_via_sidecar(
                "claude",
                "cli_browser",
            )
        assert result is None

    def test_returns_none_when_no_account(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        client = _RoutingClient(
            {
                "/backends/?": _FakeResp(200, {"items": []}),
            }
        )
        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: client):
            result = ModelDiscoveryService._discover_via_sidecar(
                "claude",
                "cli_browser",
            )
        assert result is None

    def test_picks_account_matching_auth_method(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        list_body = {
            "items": [
                {"id": "acc-key", "kind": "claude", "status": "ready", "auth_method": "api_key"},
                {
                    "id": "acc-oauth",
                    "kind": "claude",
                    "status": "ready",
                    "auth_method": "cli_browser",
                },
            ]
        }
        captured_urls = []

        class _Recorder:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url, *a, **kw):
                captured_urls.append(url)
                if "/backends/?" in url:
                    return _FakeResp(200, list_body)
                return _FakeResp(200, {"items": [{"id": "claude-x"}]})

        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: _Recorder()):
            ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        # Second call should target the OAuth account, not the API-key one.
        assert any("/acc-oauth/models" in u for u in captured_urls)

    def test_uses_bearer_auth_header_not_x_api_key(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        list_body = {"items": [{"id": "acc-1", "kind": "claude", "status": "ready"}]}
        captured_headers = []

        class _Recorder:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url, *a, **kw):
                captured_headers.append(kw.get("headers", {}))
                if "/backends/?" in url:
                    return _FakeResp(200, list_body)
                return _FakeResp(200, {"items": [{"id": "claude-x"}]})

        with _admin_key_patch(), patch("httpx.Client", lambda *a, **kw: _Recorder()):
            ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        # Sidecar's LazyFlaskKeyAuth uses Authorization: Bearer, NOT X-API-Key.
        for hdrs in captured_headers:
            assert hdrs.get("Authorization", "").startswith("Bearer ")
            assert "X-API-Key" not in hdrs
