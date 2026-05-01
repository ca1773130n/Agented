"""Smoke tests for the admin-misc batch (wave 49)."""

from litestar.testing import create_test_client

from app_litestar.routes.admin_misc import admin_misc_router


def _client():
    return create_test_client(route_handlers=[admin_misc_router])


def test_execution_search_returns_envelope(isolated_db):
    with _client() as c:
        resp = c.get("/admin/execution-search?q=test")
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body and "query" in body and body["query"] == "test"


def test_execution_search_stats(isolated_db):
    with _client() as c:
        resp = c.get("/admin/execution-search/stats")
    assert resp.status_code == 200


def test_rotation_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rotation/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body and "evaluator" in body


def test_rotation_history(isolated_db):
    with _client() as c:
        resp = c.get("/admin/rotation/history")
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body and "total_count" in body


def test_specialized_bot_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/specialized-bots/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "bots" in body and isinstance(body["bots"], list)


def test_specialized_bot_health(isolated_db):
    with _client() as c:
        resp = c.get("/admin/specialized-bots/health")
    assert resp.status_code == 200
