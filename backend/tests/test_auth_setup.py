"""Tests for unified DB-backed auth gate."""

from app.db.rbac import create_user_role, generate_api_key


class TestUnifiedAuthGate:
    """Auth gate uses user_roles table instead of env var."""

    def test_no_roles_in_db_allows_all_requests(self, client, isolated_db):
        """When no API keys exist, all requests pass (bootstrap mode)."""
        resp = client.get("/admin/triggers")
        assert resp.status_code != 401

    def test_with_roles_rejects_missing_key(self, client, isolated_db):
        """When keys exist, requests without X-API-Key are rejected."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers")
        assert resp.status_code == 401

    def test_with_roles_rejects_invalid_key(self, client, isolated_db):
        """When keys exist, invalid X-API-Key is rejected."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_with_roles_accepts_valid_key(self, client, isolated_db):
        """When keys exist, valid X-API-Key is accepted."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/admin/triggers", headers={"X-API-Key": key})
        assert resp.status_code != 401

    def test_health_endpoints_bypass_auth(self, client, isolated_db):
        """Health endpoints always bypass auth."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        for path in ["/health/liveness", "/health/readiness", "/health/auth-status"]:
            resp = client.get(path)
            assert resp.status_code != 401, f"{path} should bypass auth"

    def test_docs_bypass_auth(self, client, isolated_db):
        """Docs endpoints bypass auth."""
        key = generate_api_key()
        create_user_role(key, "Admin", "admin")
        resp = client.get("/docs")
        # docs may 404 but should not 401
        assert resp.status_code != 401

    def test_env_var_still_works_as_fallback(self, client, isolated_db, monkeypatch):
        """AGENTED_API_KEY env var still works for backward compat."""
        monkeypatch.setenv("AGENTED_API_KEY", "env-key-123")
        resp = client.get("/admin/triggers", headers={"X-API-Key": "env-key-123"})
        assert resp.status_code != 401
