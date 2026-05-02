"""Smoke tests for the Litestar scheduler routes (wave 51)."""

from litestar.testing import create_test_client

from app_litestar.routes.scheduler import scheduler_router


def _client():
    return create_test_client(route_handlers=[scheduler_router])


def test_status(isolated_db):
    with _client() as c:
        resp = c.get("/admin/scheduler/status")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


def test_sessions(isolated_db):
    with _client() as c:
        resp = c.get("/admin/scheduler/sessions")
    assert resp.status_code == 200
    assert "sessions" in resp.json()


def test_eligibility(isolated_db):
    with _client() as c:
        resp = c.get("/admin/scheduler/eligibility/1")
    assert resp.status_code == 200
