"""Smoke tests for the Litestar product_owner routes (wave 58)."""

from litestar.testing import create_test_client

from app.database import create_product
from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.product_owner import product_owner_router


def _client():
    return create_test_client(
        route_handlers=[health_router, product_owner_router],
        dependencies={"caller": provide_caller},
    )


def _seed_product():
    return create_product(name="POTest")


def test_unknown_product_404(isolated_db):
    create_user_role("admin-key-po", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/products/missing-id/decisions",
            headers={"X-API-Key": "admin-key-po"},
        )
    assert resp.status_code == 404


def test_list_decisions_for_product(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po2", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            f"/admin/products/{pid}/decisions",
            headers={"X-API-Key": "admin-key-po2"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "decisions" in body and "total_count" in body


def test_create_decision(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po3", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            f"/admin/products/{pid}/decisions",
            headers={"X-API-Key": "admin-key-po3"},
            json={"title": "Use Litestar"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["decision"]["title"] == "Use Litestar"


def test_create_decision_requires_title(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po4", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            f"/admin/products/{pid}/decisions",
            headers={"X-API-Key": "admin-key-po4"},
            json={},
        )
    assert resp.status_code == 400


def test_list_milestones(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po5", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            f"/admin/products/{pid}/milestones",
            headers={"X-API-Key": "admin-key-po5"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "milestones" in body


def test_create_milestone_requires_version_and_title(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po6", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            f"/admin/products/{pid}/milestones",
            headers={"X-API-Key": "admin-key-po6"},
            json={"version": "v1"},
        )
    assert resp.status_code == 400


def test_dashboard_endpoint(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po7", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            f"/admin/products/{pid}/dashboard",
            headers={"X-API-Key": "admin-key-po7"},
        )
    assert resp.status_code == 200


def test_assign_owner_requires_id(isolated_db):
    pid = _seed_product()
    create_user_role("admin-key-po8", "Admin", "admin")
    with _client() as c:
        resp = c.put(
            f"/admin/products/{pid}/owner",
            headers={"X-API-Key": "admin-key-po8"},
            json={},
        )
    assert resp.status_code == 400
