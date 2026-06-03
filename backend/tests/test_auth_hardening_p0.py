"""Regression tests for the P0/P1 auth-hardening pass.

Covers:
  - C1: secret-vault reveal/list gated at admin (not editor/viewer).
  - M1: bootstrap mode fails CLOSED without AGENTED_ALLOW_BOOTSTRAP=1.
  - H3: env API key authenticates as an attributable service principal.
"""

import pytest
from litestar.testing import create_test_client


def _setup_user_with_role(role: str, email: str = "u@test") -> str:
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (email, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    assert create_user_role(api_key, label="t", role=role, user_id=email) is not None
    return api_key


def _client():
    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.admin_tooling import secrets_router

    return create_test_client(route_handlers=[secrets_router], middleware=[ApiKeyMiddleware()])


class TestSecretVaultRequiresAdmin:
    def test_editor_cannot_list_secrets(self, isolated_db):
        api_key = _setup_user_with_role("editor")
        with _client() as c:
            resp = c.get("/admin/secrets/", headers={"X-API-Key": api_key})
        assert resp.status_code == 403

    def test_editor_cannot_reveal_secret(self, isolated_db):
        api_key = _setup_user_with_role("editor")
        with _client() as c:
            resp = c.post("/admin/secrets/sec-abc123/reveal", headers={"X-API-Key": api_key})
        assert resp.status_code == 403

    def test_viewer_cannot_list_secrets(self, isolated_db):
        api_key = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.get("/admin/secrets/", headers={"X-API-Key": api_key})
        assert resp.status_code == 403


class TestBootstrapFailsClosed:
    def test_no_keys_no_flag_is_unauthorized(self, isolated_db, monkeypatch):
        # Override the conftest autouse opt-in: with neither roles, env key, nor
        # the flag, the request must be rejected (fail-closed), not allowed.
        monkeypatch.delenv("AGENTED_ALLOW_BOOTSTRAP", raising=False)
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        with _client() as c:
            resp = c.get("/admin/secrets/")
        assert resp.status_code == 401

    def test_bootstrap_does_not_open_admin_guarded_vault(self, isolated_db, monkeypatch):
        # Even in explicit bootstrap mode, the per-route admin guard on the
        # secret vault stays closed (no real principal). Bootstrap UX is served
        # by ungated routes; the most sensitive surface is never auto-opened.
        monkeypatch.setenv("AGENTED_ALLOW_BOOTSTRAP", "1")
        monkeypatch.delenv("AGENTED_API_KEY", raising=False)
        with _client() as c:
            resp = c.get("/admin/secrets/")
        assert resp.status_code == 403


class TestEnvKeyPrincipal:
    def test_env_key_authenticates_as_service_principal(self, isolated_db, monkeypatch):
        # A real (DB) role exists so bootstrap doesn't apply; env key must still
        # authenticate as admin via the break-glass path.
        _setup_user_with_role("viewer", email="someone@test")
        monkeypatch.setenv("AGENTED_API_KEY", "env-break-glass-key")
        monkeypatch.delenv("AGENTED_ALLOW_BOOTSTRAP", raising=False)
        with _client() as c:
            resp = c.get("/admin/secrets/", headers={"X-API-Key": "env-break-glass-key"})
        # admin-authenticated; vault unconfigured -> 503, never 401/403.
        assert resp.status_code not in (401, 403)
