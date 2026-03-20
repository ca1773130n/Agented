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


class TestSetupEndpoint:
    """POST /health/setup generates the first admin API key."""

    def test_setup_creates_admin_key_when_no_keys_exist(self, client, isolated_db):
        """First call creates admin key and returns it."""
        resp = client.post("/health/setup", json={"label": "My Admin Key"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert "api_key" in data
        assert len(data["api_key"]) == 64
        assert data["role"] == "admin"
        assert data["label"] == "My Admin Key"

    def test_setup_rejected_when_keys_exist(self, client, isolated_db):
        """Setup is locked after first key is created."""
        client.post("/health/setup", json={"label": "First"})
        resp = client.post("/health/setup", json={"label": "Second"})
        assert resp.status_code == 403
        data = resp.get_json()
        assert "already configured" in data["error"].lower()

    def test_setup_default_label(self, client, isolated_db):
        """Label defaults to 'Admin' when not provided."""
        resp = client.post("/health/setup", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["label"] == "Admin"

    def test_setup_key_works_for_auth(self, client, isolated_db):
        """The generated key can be used to authenticate."""
        setup_resp = client.post("/health/setup", json={"label": "Admin"})
        key = setup_resp.get_json()["api_key"]
        resp = client.get("/admin/triggers", headers={"X-API-Key": key})
        assert resp.status_code != 401
