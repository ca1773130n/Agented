"""v0.7.7: /admin/super-agents/.../activity + .../rollup endpoint tests."""

from __future__ import annotations

import pytest


def _setup_admin_user(email: str = "ad@test"):
    """Plant an admin user/role and return its API key."""
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
    role_id = create_user_role(api_key, label="t", role="admin", user_id=user_id)
    assert role_id is not None
    return api_key


@pytest.fixture
def client(isolated_db):
    """Test client mounting the super_agent_activity router with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.super_agent_activity import super_agent_activity_router

    with create_test_client(
        route_handlers=[super_agent_activity_router],
        middleware=[ApiKeyMiddleware()],
    ) as c:
        yield c


def _admin_headers():
    api_key = _setup_admin_user()
    return {"X-API-Key": api_key}


def test_list_activity_returns_events(client):
    from app.services import super_agent_activity_service

    super_agent_activity_service.record(
        super_agent_id="sa-1",
        event_type="message_turn",
        payload={"role": "user"},
    )
    headers = _admin_headers()
    r = client.get("/admin/super-agents/sa-1/activity", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert len(body["events"]) == 1
    assert body["events"][0]["event_type"] == "message_turn"


def test_list_activity_filters_by_types(client):
    from app.services import super_agent_activity_service

    super_agent_activity_service.record(
        super_agent_id="sa-1", event_type="message_turn", payload={}
    )
    super_agent_activity_service.record(
        super_agent_id="sa-1", event_type="tool_call", payload={}
    )
    super_agent_activity_service.record(
        super_agent_id="sa-1", event_type="git_action", payload={}
    )
    headers = _admin_headers()
    r = client.get(
        "/admin/super-agents/sa-1/activity?types=message_turn,tool_call",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 2
    assert {e["event_type"] for e in body["events"]} == {"message_turn", "tool_call"}


def test_list_activity_respects_limit(client):
    from app.services import super_agent_activity_service

    for _ in range(5):
        super_agent_activity_service.record(
            super_agent_id="sa-1", event_type="t", payload={}
        )
    headers = _admin_headers()
    r = client.get("/admin/super-agents/sa-1/activity?limit=2", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["events"]) == 2


def test_rollup_returns_dict(client):
    from app.services import super_agent_activity_service

    super_agent_activity_service.record(
        super_agent_id="sa-1", event_type="t", payload={}, cost_usd=0.05
    )
    headers = _admin_headers()
    r = client.get("/admin/super-agents/sa-1/rollup", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["super_agent_id"] == "sa-1"
    assert body["event_count"] == 1
    assert body["total_cost_usd"] == 0.05
    assert body["status_pill"] == "active"


def test_rollup_invalid_window_returns_400(client):
    headers = _admin_headers()
    r = client.get("/admin/super-agents/sa-1/rollup?window_days=0", headers=headers)
    assert r.status_code == 400
    r = client.get("/admin/super-agents/sa-1/rollup?window_days=91", headers=headers)
    assert r.status_code == 400


def test_rollup_idle_for_empty(client):
    headers = _admin_headers()
    r = client.get("/admin/super-agents/sa-empty/rollup", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status_pill"] == "idle"
    assert body["event_count"] == 0


def test_session_activity_returns_session_events(client):
    from app.services import super_agent_activity_service

    super_agent_activity_service.record(
        super_agent_id="sa-1",
        session_id="sess-A",
        event_type="message_turn",
        payload={},
    )
    super_agent_activity_service.record(
        super_agent_id="sa-1",
        session_id="sess-B",
        event_type="tool_call",
        payload={},
    )
    headers = _admin_headers()
    r = client.get(
        "/admin/super-agents/sessions/sess-A/activity", headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["session_id"] == "sess-A"


def test_endpoints_require_admin(client):
    """Unauthenticated requests must not reach the handler."""
    r = client.get("/admin/super-agents/sa-1/activity")
    assert r.status_code in (401, 403)
    r = client.get("/admin/super-agents/sa-1/rollup")
    assert r.status_code in (401, 403)
    r = client.get("/admin/super-agents/sessions/s/activity")
    assert r.status_code in (401, 403)
