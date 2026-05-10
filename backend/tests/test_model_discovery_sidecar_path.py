"""v0.7.9: sidecar-backed model discovery tests."""

from unittest.mock import patch

import httpx

from app.services.model_discovery_service import ModelDiscoveryService


class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def get(self, *a, **kw):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _patch(response, accounts=(("acc-1", "cli_browser"),)):
    return [
        patch(
            "app.db.backends.get_backend_accounts",
            return_value=[{"id": aid, "auth_method": auth} for (aid, auth) in accounts],
        ),
        patch(
            "httpx.Client",
            lambda *a, **kw: _FakeClient(response),
        ),
    ]


class TestSidecarDiscovery:
    def test_returns_models_on_200(self, isolated_db):
        body = {"items": [{"id": "claude-opus-4-7"}, {"id": "claude-sonnet-4-7"}]}
        patches = _patch(_FakeResp(200, body))
        for p in patches:
            p.start()
        try:
            result = ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        finally:
            for p in patches:
                p.stop()
        assert result == ["claude-opus-4-7", "claude-sonnet-4-7"]

    def test_returns_none_on_500(self, isolated_db):
        patches = _patch(_FakeResp(500, {"detail": "boom"}))
        for p in patches:
            p.start()
        try:
            result = ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        finally:
            for p in patches:
                p.stop()
        assert result is None

    def test_returns_none_on_timeout(self, isolated_db):
        patches = _patch(httpx.TimeoutException("slow"))
        for p in patches:
            p.start()
        try:
            result = ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        finally:
            for p in patches:
                p.stop()
        assert result is None

    def test_returns_none_when_no_account(self, isolated_db):
        patches = _patch(_FakeResp(200, {"items": []}), accounts=())
        for p in patches:
            p.start()
        try:
            result = ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        finally:
            for p in patches:
                p.stop()
        assert result is None

    def test_picks_account_matching_auth_method(self, isolated_db):
        body = {"items": [{"id": "claude-x"}]}
        accounts = (("acc-key", "api_key"), ("acc-oauth", "cli_browser"))
        captured_url = []

        class _Recorder:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def get(self, url, *a, **kw):
                captured_url.append(url)
                return _FakeResp(200, body)

        patches = [
            patch(
                "app.db.backends.get_backend_accounts",
                return_value=[{"id": aid, "auth_method": auth} for (aid, auth) in accounts],
            ),
            patch("httpx.Client", lambda *a, **kw: _Recorder()),
        ]
        for p in patches:
            p.start()
        try:
            ModelDiscoveryService._discover_via_sidecar("claude", "cli_browser")
        finally:
            for p in patches:
                p.stop()
        assert "/acc-oauth/models" in captured_url[0]
