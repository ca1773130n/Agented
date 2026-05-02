"""Smoke tests for Litestar budgets routes (wave 59)."""

from litestar.testing import create_test_client

from app_litestar.routes.budgets import budgets_router


def _client():
    return create_test_client(route_handlers=[budgets_router])


def test_window_usage(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/window-usage")
    assert resp.status_code == 200


def test_list_limits_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/limits")
    assert resp.status_code == 200
    body = resp.json()
    assert "limits" in body and "total_count" in body


def test_get_limit_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/limits/agent/missing-id")
    assert resp.status_code == 404


def test_set_limit_validates_entity_type(isolated_db):
    with _client() as c:
        resp = c.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "ghost",
                "entity_id": "x",
                "soft_limit_usd": 1.0,
            },
        )
    assert resp.status_code == 400


def test_set_limit_validates_period(isolated_db):
    with _client() as c:
        resp = c.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "agent",
                "entity_id": "agent-x",
                "period": "yearly",
                "soft_limit_usd": 1.0,
            },
        )
    assert resp.status_code == 400


def test_set_limit_requires_at_least_one_threshold(isolated_db):
    with _client() as c:
        resp = c.put(
            "/admin/budgets/limits",
            json={"entity_type": "agent", "entity_id": "agent-x"},
        )
    assert resp.status_code == 400


def test_estimate_requires_prompt(isolated_db):
    with _client() as c:
        resp = c.post("/admin/budgets/estimate", json={})
    assert resp.status_code == 400


def test_check_requires_entity(isolated_db):
    with _client() as c:
        resp = c.post("/admin/budgets/check", json={})
    assert resp.status_code == 400


def test_usage_summary_validates_group_by(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/usage/summary?group_by=quarter")
    assert resp.status_code == 400


def test_history_stats_validates_period(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/usage/history-stats?period=hourly")
    assert resp.status_code == 400


def test_all_time_usage(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/usage/all-time")
    assert resp.status_code == 200
    assert "total_cost_usd" in resp.json()


def test_session_stats_no_cache(isolated_db):
    with _client() as c:
        resp = c.get("/admin/budgets/session-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "stats" in body
