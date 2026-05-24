"""Smoke tests for the wave 67 leaf CRUD batch."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.leaf_crud_c import (
    analytics_router,
    config_export_router,
    findings_router,
    products_router,
    report_digests_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            products_router,
            analytics_router,
            findings_router,
            report_digests_router,
            config_export_router,
        ],
        dependencies={"caller": provide_caller},
    )


# Products


def test_list_products_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/products/")
    assert resp.status_code == 200


def test_unknown_product_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/products/missing")
    assert resp.status_code == 404


def test_create_product_requires_name(isolated_db):
    with _client() as c:
        resp = c.post("/admin/products/", json={})
    assert resp.status_code == 400


def test_update_unknown_product_404(isolated_db):
    with _client() as c:
        resp = c.put("/admin/products/missing", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_unknown_product_404(isolated_db):
    with _client() as c:
        resp = c.delete("/admin/products/missing")
    assert resp.status_code == 404


# Analytics


def test_cost_analytics(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/cost")
    assert resp.status_code == 200


def test_cost_analytics_invalid_group_by(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/cost?group_by=year")
    assert resp.status_code == 400


def test_execution_analytics(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/executions")
    assert resp.status_code == 200


def test_team_leaderboard(isolated_db):
    with _client() as c:
        resp = c.get("/admin/analytics/team-leaderboard")
    assert resp.status_code == 200


# Findings


def test_list_findings_empty(isolated_db):
    with _client() as c:
        resp = c.get("/api/findings/")
    assert resp.status_code == 200


def test_create_finding_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/api/findings/", json={})
    assert resp.status_code == 400


def test_update_unknown_finding_404(isolated_db):
    with _client() as c:
        resp = c.patch("/api/findings/missing", json={"status": "resolved"})
    assert resp.status_code == 404


def test_delete_unknown_finding_404(isolated_db):
    with _client() as c:
        resp = c.delete("/api/findings/missing")
    assert resp.status_code == 404


# Report digests


# PR-G: silent-success stubs flipped to 501. The GET /digests read stays as
# an honest empty 200 — the UI renders an empty state for it. The create and
# update handlers previously echoed input back as if persisted; they now
# return 501 ("Feature not yet enabled") so the UI can render a banner.


def test_list_digests_returns_empty_200(isolated_db):
    with _client() as c:
        resp = c.get("/admin/reports/digests")
    assert resp.status_code == 200
    assert resp.json() == {"digests": []}


def test_create_digest_returns_501(isolated_db):
    with _client() as c:
        resp = c.post("/admin/reports/digests", json={"team_name": "Demo"})
    assert resp.status_code == 501


def test_update_digest_returns_501(isolated_db):
    with _client() as c:
        resp = c.put("/admin/reports/digests/team-x", json={"enabled": True})
    assert resp.status_code == 501


# Config export/import


def test_export_unknown_trigger_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/export")
    assert resp.status_code == 404


def test_export_invalid_format(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/missing/export?format=xml")
    assert resp.status_code == 400


def test_import_requires_body(isolated_db):
    with _client() as c:
        resp = c.post("/admin/triggers/import", json={})
    assert resp.status_code == 400


def test_validate_config_requires_format(isolated_db):
    with _client() as c:
        resp = c.post("/admin/triggers/validate-config", json={"config": "name: x"})
    assert resp.status_code == 400


def test_export_all_requires_valid_format(isolated_db):
    with _client() as c:
        resp = c.get("/admin/triggers/export-all?format=xml")
    assert resp.status_code == 400
