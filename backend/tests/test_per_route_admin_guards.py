"""v0.5.12: per-route requires_role('admin') overrides on sensitive POST routes.

Verifies that the two subprocess-touching POST routes which bypass the
coarse editor-gate (or are under /api/ with no coarse gate at all)
correctly enforce admin-only access via the Litestar guard.

Tested routes:
  - POST /api/setup/bundle-install   (guards=[requires_role('admin')])
  - POST /admin/backends/{id}/install (guards=[requires_role('admin')])
"""

from __future__ import annotations


def _setup_user_with_role(role: str, email: str = "u@test"):
    """Returns (user_id, api_key, session_token)."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key
    from app.db.sessions import create_session

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role=role, user_id=user_id)
    assert role_id is not None
    sess = create_session(user_id)
    return user_id, api_key, sess["token"]


def _setup_client():
    """Test client mounting the setup router (bundle-install) with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.leaf_crud_i import setup_router

    return create_test_client(
        route_handlers=[setup_router],
        middleware=[ApiKeyMiddleware()],
    )


def _backends_client():
    """Test client mounting the backends router (backend install) with ApiKeyMiddleware."""
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.leaf_crud_h import backends_router

    return create_test_client(
        route_handlers=[backends_router],
        middleware=[ApiKeyMiddleware()],
    )


class TestBundleInstallAdminGuard:
    """POST /api/setup/bundle-install must require admin (it lives under /api/, so
    the coarse middleware table provides NO role gate — only the per-route guard does)."""

    def test_editor_cannot_call_bundle_install(self, isolated_db):
        _, editor_key, _ = _setup_user_with_role("editor", email="ed@test")
        with _setup_client() as c:
            resp = c.post(
                "/api/setup/bundle-install",
                headers={"X-API-Key": editor_key},
            )
        assert resp.status_code == 403

    def test_viewer_cannot_call_bundle_install(self, isolated_db):
        _, viewer_key, _ = _setup_user_with_role("viewer", email="vi@test")
        with _setup_client() as c:
            resp = c.post(
                "/api/setup/bundle-install",
                headers={"X-API-Key": viewer_key},
            )
        assert resp.status_code == 403

    def test_admin_passes_guard_for_bundle_install(self, isolated_db):
        """Admin clears the guard — the route itself may fail for other reasons
        (e.g. service logic), but it must NOT return 403."""
        _, admin_key, _ = _setup_user_with_role("admin", email="ad@test")
        with _setup_client() as c:
            resp = c.post(
                "/api/setup/bundle-install",
                headers={"X-API-Key": admin_key},
            )
        assert resp.status_code != 403


class TestBackendInstallAdminGuard:
    """POST /admin/backends/{id}/install must require admin.

    The coarse rule gives POST /admin/* only 'editor' — the per-route guard
    upgrades this to 'admin'.
    """

    def test_editor_cannot_call_backend_install(self, isolated_db):
        _, editor_key, _ = _setup_user_with_role("editor", email="ed2@test")
        with _backends_client() as c:
            resp = c.post(
                "/admin/backends/some-backend/install",
                headers={"X-API-Key": editor_key},
            )
        assert resp.status_code == 403

    def test_admin_passes_guard_for_backend_install(self, isolated_db):
        """Admin clears the guard — the route itself may fail for other reasons
        (e.g. backend not found), but it must NOT return 403."""
        _, admin_key, _ = _setup_user_with_role("admin", email="ad2@test")
        with _backends_client() as c:
            resp = c.post(
                "/admin/backends/some-backend/install",
                headers={"X-API-Key": admin_key},
            )
        assert resp.status_code != 403
