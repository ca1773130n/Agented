"""v0.5.14: rate-limit middleware coverage of /api/* and /admin/*.

Tests cover per-IP keying (unauthed), per-key keying (authed), key
isolation, per-route override beats default, 429 response shape,
env-driven defaults, regression of webhook rules, and health-bypass.
"""
from importlib import reload
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Force a fresh fixed-window state between tests."""
    from app_litestar import middleware as mw
    from app_litestar.rate_limit_guard import clear_overrides
    mw._limiter = mw._FixedWindowLimiter()
    clear_overrides()
    yield
    mw._limiter = mw._FixedWindowLimiter()
    clear_overrides()


def _make_scope(method: str, path: str, *, ip: str = "1.2.3.4",
                principal: dict | None = None) -> dict:
    headers = [(b"x-forwarded-for", ip.encode("latin-1"))]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "state": {"principal": principal} if principal else {},
        "client": ("0.0.0.0", 12345),
    }
    return scope


class _StubSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


async def _stub_next(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _drive(method: str, path: str, *, ip="1.2.3.4", principal=None) -> int:
    """Runs ApiKeyMiddleware-skipped path: just RateLimitMiddleware."""
    from app_litestar.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    scope = _make_scope(method, path, ip=ip, principal=principal)
    sender = _StubSend()
    await mw.handle(scope, None, sender, _stub_next)
    for m in sender.messages:
        if m["type"] == "http.response.start":
            return m["status"]
    return 0


@pytest.mark.asyncio
class TestPerIPKeying:
    async def test_unauthed_requests_share_per_ip_budget(self):
        # GET /api/foo — coarse default 60/min. Drive 60 hits, then 1 more.
        for _ in range(60):
            assert await _drive("GET", "/api/foo", ip="9.9.9.9") == 200
        # 61st should 429.
        assert await _drive("GET", "/api/foo", ip="9.9.9.9") == 429

    async def test_different_ips_have_separate_budgets(self):
        for _ in range(60):
            await _drive("GET", "/api/foo", ip="1.1.1.1")
        # Different IP — fresh budget.
        assert await _drive("GET", "/api/foo", ip="2.2.2.2") == 200


@pytest.mark.asyncio
class TestPerKeyKeying:
    async def test_authed_requests_use_user_id_key(self):
        principal = {"user_id": "user-A", "role": "viewer"}
        for _ in range(60):
            assert await _drive("GET", "/api/foo", principal=principal) == 200
        assert await _drive("GET", "/api/foo", principal=principal) == 429

    async def test_different_users_have_separate_budgets(self):
        a = {"user_id": "user-A", "role": "viewer"}
        b = {"user_id": "user-B", "role": "viewer"}
        for _ in range(60):
            await _drive("GET", "/api/foo", principal=a)
        # User B has not consumed any budget.
        assert await _drive("GET", "/api/foo", principal=b) == 200

    async def test_same_user_different_ips_share_budget(self):
        principal = {"user_id": "user-A", "role": "viewer"}
        for _ in range(60):
            await _drive("GET", "/api/foo", ip="1.1.1.1", principal=principal)
        # Same key, different IP — should still 429 (key wins).
        assert await _drive("GET", "/api/foo", ip="2.2.2.2", principal=principal) == 429


@pytest.mark.asyncio
class TestPerRouteOverride:
    async def test_override_is_tighter_than_default(self):
        from app_litestar.rate_limit_guard import register_override
        register_override("POST", "/api/auth/login", 5, 60.0)
        # 5 hits ok, 6th 429 — even though /api/* coarse default is 30/min.
        for _ in range(5):
            assert await _drive("POST", "/api/auth/login", ip="3.3.3.3") == 200
        assert await _drive("POST", "/api/auth/login", ip="3.3.3.3") == 429


@pytest.mark.asyncio
class TestResponseShape:
    async def test_429_includes_retry_after_header(self):
        from app_litestar.middleware import RateLimitMiddleware
        from app_litestar.rate_limit_guard import register_override
        register_override("POST", "/api/test", 1, 60.0)
        await _drive("POST", "/api/test", ip="4.4.4.4")
        # Hit it again — second request should 429.
        mw = RateLimitMiddleware()
        scope = _make_scope("POST", "/api/test", ip="4.4.4.4")
        sender = _StubSend()
        await mw.handle(scope, None, sender, _stub_next)
        start = next(m for m in sender.messages if m["type"] == "http.response.start")
        assert start["status"] == 429
        header_names = [h[0] for h in start["headers"]]
        assert b"retry-after" in header_names

    async def test_429_body_has_rate_limited_code(self):
        import json as _json
        from app_litestar.middleware import RateLimitMiddleware
        from app_litestar.rate_limit_guard import register_override
        register_override("POST", "/api/foo", 1, 60.0)
        await _drive("POST", "/api/foo", ip="5.5.5.5")
        mw = RateLimitMiddleware()
        scope = _make_scope("POST", "/api/foo", ip="5.5.5.5")
        sender = _StubSend()
        await mw.handle(scope, None, sender, _stub_next)
        body_msg = next(m for m in sender.messages if m["type"] == "http.response.body")
        body = _json.loads(body_msg["body"])
        assert body["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
class TestRegression:
    async def test_webhook_route_preserves_30_per_min(self):
        # GitHub webhook keeps its dedicated rule.
        for _ in range(30):
            assert await _drive("POST", "/api/webhooks/github", ip="6.6.6.6") == 200
        assert await _drive("POST", "/api/webhooks/github", ip="6.6.6.6") == 429

    async def test_health_endpoint_is_not_rate_limited(self):
        # /health/* doesn't match any /api/* or /admin/* rule.
        for _ in range(200):
            assert await _drive("GET", "/health/liveness", ip="7.7.7.7") == 200


class TestEnvDrivenDefaults:
    """Module-level _RATE_LIMITS is built at import time from env vars.
    Validating the parser via direct unit test rather than re-importing
    the middleware module (which has stateful side-effects)."""

    def test_int_env_returns_default_when_unset(self, monkeypatch):
        from app_litestar.middleware import _int_env
        monkeypatch.delenv("RATE_LIMIT_TEST_VAR", raising=False)
        assert _int_env("RATE_LIMIT_TEST_VAR", 99) == 99

    def test_int_env_returns_parsed_int_when_set(self, monkeypatch):
        from app_litestar.middleware import _int_env
        monkeypatch.setenv("RATE_LIMIT_TEST_VAR", "7")
        assert _int_env("RATE_LIMIT_TEST_VAR", 99) == 7

    def test_int_env_falls_back_on_garbage(self, monkeypatch):
        from app_litestar.middleware import _int_env
        monkeypatch.setenv("RATE_LIMIT_TEST_VAR", "not-a-number")
        assert _int_env("RATE_LIMIT_TEST_VAR", 99) == 99
