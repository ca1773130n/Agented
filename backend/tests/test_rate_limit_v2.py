"""v0.5.14: rate-limit middleware coverage of /api/* and /admin/*.

Tests cover per-IP keying (unauthed), per-key keying (authed), key
isolation, per-route override beats default, 429 response shape,
env-driven defaults, regression of webhook rules, and health-bypass.
"""

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


def _make_scope(
    method: str, path: str, *, ip: str = "1.2.3.4", principal: dict | None = None
) -> dict:
    # X-Forwarded-For is no longer trusted by default (it is spoofable); the
    # rate limiter keys on the real socket peer unless AGENTED_TRUST_PROXY=1.
    # Set the peer to `ip` so the per-IP keying tests exercise the production
    # path. The XFF header is still present but intentionally ignored.
    headers = [(b"x-forwarded-for", ip.encode("latin-1"))]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "state": {"principal": principal} if principal else {},
        "client": (ip, 12345),
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

    async def test_spoofed_xff_does_not_mint_fresh_budget(self, monkeypatch):
        # Security: with no trusted proxy, rotating X-Forwarded-For must NOT
        # create new buckets — all requests from the same socket peer share one
        # budget regardless of the spoofable header.
        monkeypatch.delenv("AGENTED_TRUST_PROXY", raising=False)
        same_peer = ("203.0.113.7", 5555)

        async def drive_with_xff(xff: str) -> int:
            from app_litestar.middleware import RateLimitMiddleware

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/foo",
                "headers": [(b"x-forwarded-for", xff.encode("latin-1"))],
                "state": {},
                "client": same_peer,
            }
            status = {"code": 200}

            async def sender(msg):
                if msg["type"] == "http.response.start":
                    status["code"] = msg["status"]

            await RateLimitMiddleware().handle(scope, None, sender, _stub_next)
            return status["code"]

        for i in range(60):
            assert await drive_with_xff(f"10.0.0.{i}") == 200
        # 61st request, yet another spoofed XFF, same socket peer → throttled.
        assert await drive_with_xff("10.0.0.250") == 429


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


@pytest.mark.asyncio
class TestFullStackOrdering:
    """v0.5.14 Codex round-1 fix: ApiKeyMiddleware must run BEFORE
    RateLimitMiddleware so principal is in scope when the rate-limit
    middleware resolves the per-user budget."""

    async def test_authed_request_uses_user_key_not_ip(self, isolated_db):
        """Drives the real Litestar stack: api-key auth, role check,
        rate-limit. Verifies that two API keys for the SAME user share
        a budget (key wins over IP)."""
        from litestar import get
        from litestar.testing import create_test_client

        from app.database import get_connection
        from app.db.rbac import create_user_role, generate_api_key
        from app_litestar.middleware import ApiKeyMiddleware, RateLimitMiddleware
        from app_litestar.rate_limit_guard import (
            clear_overrides,
            register_override,
        )

        clear_overrides()
        # Tighten /api/* GET so we hit the limit fast.
        register_override("GET", "/api/probe", 3, 60.0)

        @get("/api/probe", sync_to_thread=False)
        def probe() -> dict:
            return {"ok": True}

        # Provision two API keys belonging to the SAME user.
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                ("u-shared", "u@shared", "x"),
            )
            conn.commit()
        api_key_1 = generate_api_key()
        api_key_2 = generate_api_key()
        create_user_role(api_key_1, label="k1", role="viewer", user_id="u-shared")
        create_user_role(api_key_2, label="k2", role="viewer", user_id="u-shared")

        with create_test_client(
            route_handlers=[probe],
            middleware=[ApiKeyMiddleware(), RateLimitMiddleware()],
        ) as client:
            # 3 requests with key 1 — all 200.
            for _ in range(3):
                assert client.get("/api/probe", headers={"X-API-Key": api_key_1}).status_code == 200
            # 4th request with key 2 — same user → SHARED budget → 429.
            r = client.get("/api/probe", headers={"X-API-Key": api_key_2})
            assert r.status_code == 429, (
                "Per-user keying broken: requests with different keys "
                "for the same user should share a rate-limit budget"
            )

        clear_overrides()

    async def test_authed_request_isolates_different_users(self, isolated_db):
        """Codex round-2 D: different users hitting the same route through
        the real stack must NOT share a budget. Pairs with the same-user
        test above which asserts the symmetric shared-budget case."""
        from litestar import get
        from litestar.testing import create_test_client

        from app.database import get_connection
        from app.db.rbac import create_user_role, generate_api_key
        from app_litestar.middleware import ApiKeyMiddleware, RateLimitMiddleware
        from app_litestar.rate_limit_guard import (
            clear_overrides,
            register_override,
        )

        clear_overrides()
        register_override("GET", "/api/probe-iso", 3, 60.0)

        @get("/api/probe-iso", sync_to_thread=False)
        def probe_iso() -> dict:
            return {"ok": True}

        with get_connection() as conn:
            for uid, email in (("u-A", "a@iso"), ("u-B", "b@iso")):
                conn.execute(
                    "INSERT OR IGNORE INTO users (id, email, password_hash, "
                    "created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (uid, email, "x"),
                )
            conn.commit()
        key_a = generate_api_key()
        key_b = generate_api_key()
        create_user_role(key_a, label="A", role="viewer", user_id="u-A")
        create_user_role(key_b, label="B", role="viewer", user_id="u-B")

        with create_test_client(
            route_handlers=[probe_iso],
            middleware=[ApiKeyMiddleware(), RateLimitMiddleware()],
        ) as client:
            # User A burns their budget.
            for _ in range(3):
                assert client.get("/api/probe-iso", headers={"X-API-Key": key_a}).status_code == 200
            assert client.get("/api/probe-iso", headers={"X-API-Key": key_a}).status_code == 429
            # User B should be unaffected.
            assert client.get("/api/probe-iso", headers={"X-API-Key": key_b}).status_code == 200, (
                "Per-user budget isolation broken: user B should have a "
                "fresh budget on a route where user A is throttled"
            )

        clear_overrides()


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
