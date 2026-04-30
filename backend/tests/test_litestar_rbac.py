"""Track A wave 23 — Litestar GET /admin/rbac/permissions parity tests."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.main import liveness
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[liveness, rbac_router],
        dependencies={"caller": provide_caller},
    )


def test_litestar_returns_permission_matrix_in_bootstrap_mode(isolated_db):
    # No roles → bootstrap mode → request without API key still allowed.
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["permissions"].keys()) == {"viewer", "operator", "editor", "admin"}
    assert "manage" in body["permissions"]["admin"]
    assert "manage" not in body["permissions"]["viewer"]


def test_litestar_requires_auth_when_roles_configured(isolated_db):
    create_user_role("real-key", "Real", "admin")
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions")
    assert resp.status_code == 401


def test_litestar_accepts_valid_key(isolated_db):
    create_user_role("good-key", "Good", "viewer")
    with _client(isolated_db) as client:
        resp = client.get("/admin/rbac/permissions", headers={"X-API-Key": "good-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["permissions"]["viewer"] == ["read"]


def test_litestar_body_matches_flask_version(client, isolated_db):
    """Side-by-side: Flask and Litestar must return identical permission matrices."""
    create_user_role("matched-key", "Matched", "admin")

    flask_resp = client.get(
        "/admin/rbac/permissions",
        headers={"X-API-Key": "matched-key"},
    )
    assert flask_resp.status_code == 200
    flask_body = flask_resp.get_json()

    with _client(isolated_db) as ls_client:
        ls_resp = ls_client.get(
            "/admin/rbac/permissions",
            headers={"X-API-Key": "matched-key"},
        )
    assert ls_resp.status_code == 200
    ls_body = ls_resp.json()

    assert flask_body == ls_body
