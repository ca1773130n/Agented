"""Smoke tests for the Litestar /admin/triggers/* routes (wave 52)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.triggers import triggers_router


def _client():
    return create_test_client(
        route_handlers=[health_router, triggers_router],
        dependencies={"caller": provide_caller},
    )


def test_list_triggers_bootstrap_mode(isolated_db):
    """No roles → bootstrap admin → list returns triggers."""
    with _client() as c:
        resp = c.get("/admin/triggers/")
    assert resp.status_code == 200
    assert "triggers" in resp.json()


def test_list_triggers_with_admin_key(isolated_db):
    create_user_role("admin-key-tr", "Admin", "admin")
    with _client() as c:
        resp = c.get("/admin/triggers/", headers={"X-API-Key": "admin-key-tr"})
    assert resp.status_code == 200


def test_list_triggers_without_key_after_setup_returns_401(isolated_db):
    create_user_role("admin-key-tr2", "Admin", "admin")
    with _client() as c:
        resp = c.get("/admin/triggers/")
    assert resp.status_code == 401


def test_unknown_trigger_returns_404(isolated_db):
    create_user_role("admin-key-tr3", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/admin/triggers/missing-id",
            headers={"X-API-Key": "admin-key-tr3"},
        )
    # Service returns NOT_FOUND tuple — we map to 404 via _result_or_raise.
    assert resp.status_code == 404


def test_run_trigger_unknown_id_returns_404(isolated_db):
    create_user_role("admin-key-tr4", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/triggers/missing-id/run",
            headers={"X-API-Key": "admin-key-tr4"},
            json={"message": "ping"},
        )
    assert resp.status_code in (400, 404)


def test_validate_cron_valid_expression(isolated_db):
    create_user_role("admin-key-tr5", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/triggers/validate-cron",
            headers={"X-API-Key": "admin-key-tr5"},
            json={"expression": "0 0 * * *"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["valid"] is True
    assert "next_fires" in body


def test_validate_cron_invalid_expression(isolated_db):
    create_user_role("admin-key-tr6", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/triggers/validate-cron",
            headers={"X-API-Key": "admin-key-tr6"},
            json={"expression": "not-a-cron"},
        )
    assert resp.status_code == 400


def test_create_trigger_requires_body(isolated_db):
    create_user_role("admin-key-tr7", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/triggers/",
            headers={"X-API-Key": "admin-key-tr7"},
            json={},
        )
    # Empty dict is falsy in Python — treated as "JSON body required".
    assert resp.status_code == 400


def test_generate_stream_short_description_400(isolated_db):
    create_user_role("admin-key-tr8", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/triggers/generate/stream",
            headers={"X-API-Key": "admin-key-tr8"},
            json={"description": "hi"},
        )
    assert resp.status_code == 400
