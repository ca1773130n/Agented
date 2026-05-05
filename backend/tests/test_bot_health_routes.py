"""v0.7.0: /admin/bots/health endpoint tests.

Mirrors `test_per_route_admin_guards.py` for auth wiring: spin up a
TestClient with the bot_health_router + ApiKeyMiddleware, plant a
real admin user/role in the DB, then call with X-API-Key.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _setup_user_with_role(role: str, email: str = "u@test"):
    """Returns (user_id, api_key)."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role=role, user_id=user_id)
    assert role_id is not None
    return user_id, api_key


def _client():
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.bot_health import bot_health_router

    return create_test_client(
        route_handlers=[bot_health_router],
        middleware=[ApiKeyMiddleware()],
    )


def _seed_bot_with_execution():
    from app.database import get_connection

    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO triggers (id, name, group_id, detection_keyword, "
            "prompt_template, backend_type, trigger_source, created_at) "
            "VALUES ('bot-x', 'Bot X', 0, '', '', 'claude', 'manual', ?)",
            (now,),
        )
        conn.execute(
            """INSERT INTO execution_logs
               (execution_id, trigger_id, trigger_type, started_at, finished_at,
                duration_ms, backend_type, status)
               VALUES ('e-1', 'bot-x', 'manual', ?, ?, 1000, 'claude', 'success')""",
            (now, now),
        )
        conn.commit()


class TestBotHealthRoute:
    def test_health_endpoint_returns_rollups(self, isolated_db):
        _seed_bot_with_execution()
        _, admin_key = _setup_user_with_role("admin", email="ad@test")
        with _client() as c:
            r = c.get(
                "/admin/bots/health?window_days=7",
                headers={"X-API-Key": admin_key},
            )
        assert r.status_code == 200
        body = r.json()
        assert "rollups" in body
        assert body["window_days"] == 7
        assert any(item["bot_id"] == "bot-x" for item in body["rollups"])

    def test_window_days_out_of_range_returns_400(self, isolated_db):
        _, admin_key = _setup_user_with_role("admin", email="ad2@test")
        with _client() as c:
            r1 = c.get(
                "/admin/bots/health?window_days=0",
                headers={"X-API-Key": admin_key},
            )
            r2 = c.get(
                "/admin/bots/health?window_days=91",
                headers={"X-API-Key": admin_key},
            )
        assert r1.status_code == 400
        assert r2.status_code == 400

    def test_default_window_is_7_days(self, isolated_db):
        _, admin_key = _setup_user_with_role("admin", email="ad3@test")
        with _client() as c:
            r = c.get("/admin/bots/health", headers={"X-API-Key": admin_key})
        assert r.status_code == 200
        assert r.json()["window_days"] == 7

    def test_non_admin_gets_403(self, isolated_db):
        _, viewer_key = _setup_user_with_role("viewer", email="vi@test")
        with _client() as c:
            r = c.get(
                "/admin/bots/health",
                headers={"X-API-Key": viewer_key},
            )
        assert r.status_code == 403

    def test_unauthenticated_gets_401_or_403(self, isolated_db):
        with _client() as c:
            r = c.get("/admin/bots/health")
        assert r.status_code in (401, 403)
