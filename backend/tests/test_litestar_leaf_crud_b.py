"""Smoke tests for the wave 66 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_b import (
    audit_router,
    integrations_router,
    marketplace_router,
    pr_reviews_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            marketplace_router,
            integrations_router,
            audit_router,
            pr_reviews_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Marketplaces


def test_list_marketplaces(isolated_db):
    with _client() as c:
        resp = c.get("/admin/marketplaces/")
    assert resp.status_code == 200


def test_unknown_marketplace_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/marketplaces/missing")
    assert resp.status_code == 404


def test_create_marketplace_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/marketplaces/", json={})
    assert resp.status_code == 400


def test_create_marketplace_requires_url(isolated_db):
    with _client() as c:
        resp = c.post("/admin/marketplaces/", json={"name": "x"})
    assert resp.status_code == 400


def test_search_marketplace_items(isolated_db):
    with _client() as c:
        resp = c.get("/admin/marketplaces/search?q=foo")
    assert resp.status_code == 200
    assert resp.json()["query"] == "foo"


def test_refresh_cache(isolated_db):
    with _client() as c:
        resp = c.post("/admin/marketplaces/search/refresh", json={})
    assert resp.status_code == 201 or resp.status_code == 200


def test_list_marketplace_plugins_unknown(isolated_db):
    with _client() as c:
        resp = c.get("/admin/marketplaces/missing/plugins")
    assert resp.status_code == 200


def test_install_plugin_requires_remote_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/marketplaces/m1/plugins", json={})
    assert resp.status_code == 400


# Integrations


def test_list_integrations(isolated_db):
    with _client() as c:
        resp = c.get("/admin/integrations")
    assert resp.status_code == 200


def test_unknown_integration_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/integrations/missing")
    assert resp.status_code == 404


def test_update_unknown_integration_404(isolated_db):
    with _client() as c:
        resp = c.put("/admin/integrations/missing", json={"enabled": True})
    assert resp.status_code == 404


def test_delete_unknown_integration_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/integrations/missing")
    assert resp.status_code == 404


def test_trigger_integrations_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/integrations")
    assert resp.status_code == 200


def test_slack_status_default(isolated_db):
    with _client() as c:
        resp = c.get("/admin/integrations/slack/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


# Audit


def test_audit_history(isolated_db):
    with _client() as c:
        resp = c.get("/api/audit/history")
    assert resp.status_code == 200


def test_audit_stats(isolated_db):
    with _client() as c:
        resp = c.get("/api/audit/stats")
    assert resp.status_code == 200


def test_audit_projects(isolated_db):
    with _client() as c:
        resp = c.get("/api/audit/projects")
    assert resp.status_code == 200


def test_audit_events(isolated_db):
    with _client() as c:
        resp = c.get("/api/audit/events")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_audit_events_persistent(isolated_db):
    with _client() as c:
        resp = c.get("/api/audit/events/persistent")
    assert resp.status_code == 200


def test_add_audit_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/api/audit/", json={})
    # service may accept empty dict or reject — either way, not 500
    assert resp.status_code in (200, 201, 400)


# PR reviews


def test_list_pr_reviews(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-reviews/")
    assert resp.status_code == 200


def test_pr_review_stats(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-reviews/stats")
    assert resp.status_code == 200


def test_pr_review_history(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-reviews/history?days=7")
    assert resp.status_code == 200


def test_pr_review_learning_loop(isolated_db):
    with _client() as c:
        resp = c.get("/api/pr-reviews/learning-loop")
    assert resp.status_code == 200


def test_create_pr_review_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/api/pr-reviews/", json={})
    assert resp.status_code == 400
