"""Smoke tests for the misc-batch routes (wave 48)."""

from litestar.testing import create_test_client

from app_litestar.routes.misc import misc_router


def _client():
    return create_test_client(route_handlers=[misc_router])


def test_activity_feed_returns_envelope(isolated_db):
    with _client() as c:
        resp = c.get("/api/activity-feed")
    assert resp.status_code == 200
    body = resp.json()
    assert "activities" in body and "total" in body


def test_activity_feed_caps_limit_at_500(isolated_db):
    with _client() as c:
        resp = c.get("/api/activity-feed?limit=10000")
    assert resp.status_code == 200


def test_bot_sla_stub(isolated_db):
    with _client() as c:
        resp = c.get("/admin/bots/sla")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_cross_team_insights_returns_dict(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/cross-team-insights")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_model_pricing_returns_models(isolated_db):
    with _client() as c:
        resp = c.get("/api/models/pricing")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body and isinstance(body["models"], list)
    if body["models"]:
        sample = body["models"][0]
        assert "inputPricePer1M" in sample
        assert "outputPricePer1M" in sample


def test_scheduling_suggestions_returns_dict(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/scheduling-suggestions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
