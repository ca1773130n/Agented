"""v0.7.1: /admin/triggers/.../events endpoint tests."""

from __future__ import annotations

from unittest.mock import MagicMock

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
    """Test client mounting the trigger_events router with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.trigger_events import trigger_events_router

    with create_test_client(
        route_handlers=[trigger_events_router],
        middleware=[ApiKeyMiddleware()],
    ) as c:
        yield c


def _admin_headers(client_fixture):
    """Build admin headers; the fixture itself doesn't carry auth state."""
    api_key = _setup_admin_user()
    return {"X-API-Key": api_key}


def test_list_returns_events(client):
    from app.services import trigger_event_service

    trigger_event_service.record(
        trigger_id="trig-1",
        payload='{"a":1}',
        signature_header=None,
        dispatch_status="fired",
        matched=True,
    )
    headers = _admin_headers(client)
    r = client.get("/admin/triggers/trig-1/events", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert len(body["events"]) == 1


def test_get_single_event(client):
    from app.services import trigger_event_service

    eid = trigger_event_service.record(
        trigger_id="trig-1",
        payload='{"a":1}',
        signature_header=None,
        dispatch_status="fired",
        matched=True,
    )
    headers = _admin_headers(client)
    r = client.get(f"/admin/triggers/events/{eid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["payload"] == '{"a":1}'


def test_get_unknown_returns_404(client):
    headers = _admin_headers(client)
    r = client.get("/admin/triggers/events/99999", headers=headers)
    assert r.status_code == 404


def test_replay_re_dispatches(client, monkeypatch):
    from app.services import trigger_event_service

    eid = trigger_event_service.record(
        trigger_id="trig-1",
        payload='{"a":1}',
        signature_header=None,
        dispatch_status="fired",
        matched=True,
    )
    fake = MagicMock(return_value=True)
    monkeypatch.setattr(
        "app.services.execution_service.ExecutionService.dispatch_webhook_event",
        fake,
    )
    headers = _admin_headers(client)
    r = client.post(f"/admin/triggers/events/{eid}/replay", headers=headers)
    assert r.status_code == 200
    assert r.json()["fired"] is True
    fake.assert_called_once()


def test_replay_unknown_returns_404(client):
    headers = _admin_headers(client)
    r = client.post("/admin/triggers/events/99999/replay", headers=headers)
    assert r.status_code == 404


def test_endpoints_require_admin(client):
    """Unauthenticated requests must not reach the handler."""
    r = client.get("/admin/triggers/trig-1/events")
    assert r.status_code in (401, 403)
