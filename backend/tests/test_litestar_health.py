"""Tests for the Litestar /health/* routes (track A, wave 37)."""

import pytest
from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.routes.health import health_router


def _client(_isolated_db):
    return create_test_client(route_handlers=[health_router])


class TestLiveness:
    def test_returns_status_ok(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.get("/health/liveness")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestInstanceId:
    def test_returns_an_instance_id(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.get("/health/instance-id")
        assert resp.status_code == 200
        body = resp.json()
        assert "instance_id" in body
        # Conftest seeds an instance_id on db init.
        assert body["instance_id"]


class TestSetupStatus:
    """Phase 1 plan 01-01: aggregate guard prefetch for the v0.5.0 tour."""

    def _post(self, c, body):
        return c.get("/health/setup-status")

    def test_fresh_db_returns_all_false(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["instance_id"], str) and body["instance_id"]
        for field in (
            "has_workspace",
            "has_claude_account",
            "has_codex_account",
            "has_gemini_account",
            "has_opencode_account",
            "has_harness_synced",
            "has_first_product",
        ):
            assert body[field] is False, f"{field} should default to False on fresh DB"

    def test_populated_workspace_setting(self, isolated_db):
        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('workspace_root', ?)",
                ("/tmp/workspace",),
            )
            conn.commit()
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.json()["has_workspace"] is True

    def test_blank_workspace_setting_treated_as_unset(self, isolated_db):
        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('workspace_root', ?)",
                ("   ",),
            )
            conn.commit()
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.json()["has_workspace"] is False

    def test_per_backend_account_detection(self, isolated_db):
        from app.db.connection import get_connection

        # Add a Claude account, leave the other three unconfigured.
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO backend_accounts (backend_id, account_name) VALUES (?, ?)",
                ("backend-claude", "primary"),
            )
            conn.commit()
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        body = resp.json()
        assert body["has_claude_account"] is True
        assert body["has_codex_account"] is False
        assert body["has_gemini_account"] is False
        assert body["has_opencode_account"] is False

    def test_first_product_detection(self, isolated_db):
        from app.db.products import create_product

        create_product(name="Demo", description="")
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.json()["has_first_product"] is True

    def test_harness_synced_marker(self, isolated_db):
        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('harness_synced_at', ?)",
                ("2026-05-03T00:00:00Z",),
            )
            conn.commit()
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.json()["has_harness_synced"] is True

    def test_no_auth_required(self, isolated_db):
        # The setup-status endpoint must be reachable before the user has any
        # API key configured (the welcome page calls it pre-auth).
        with _client(isolated_db) as c:
            resp = c.get("/health/setup-status")
        assert resp.status_code == 200


class TestAuthStatus:
    def test_needs_setup_when_no_keys(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.get("/health/auth-status")
        body = resp.json()
        assert body["needs_setup"] is True
        assert body["auth_required"] is False
        assert body["authenticated"] is False

    def test_authenticated_with_valid_key(self, isolated_db):
        create_user_role("auth-status-key", "Lbl", "admin")
        with _client(isolated_db) as c:
            resp = c.get(
                "/health/auth-status",
                headers={"X-API-Key": "auth-status-key"},
            )
        body = resp.json()
        assert body["needs_setup"] is False
        assert body["auth_required"] is True
        assert body["authenticated"] is True

    def test_unauthenticated_when_keys_exist_but_header_missing(self, isolated_db):
        create_user_role("required-key", "Lbl", "admin")
        with _client(isolated_db) as c:
            resp = c.get("/health/auth-status")
        body = resp.json()
        assert body["needs_setup"] is False
        assert body["auth_required"] is True
        assert body["authenticated"] is False


class TestVerifyKey:
    def test_empty_body_returns_invalid(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.post("/health/verify-key", json={})
        assert resp.status_code == 200
        assert resp.json() == {"valid": False, "message": "No key provided"}

    def test_unknown_key_returns_invalid(self, isolated_db):
        create_user_role("real-key", "Real", "admin")
        with _client(isolated_db) as c:
            resp = c.post("/health/verify-key", json={"api_key": "ghost"})
        body = resp.json()
        assert body["valid"] is False

    def test_known_key_returns_valid(self, isolated_db):
        create_user_role("good-key", "Good", "admin")
        with _client(isolated_db) as c:
            resp = c.post("/health/verify-key", json={"api_key": "good-key"})
        body = resp.json()
        assert body["valid"] is True

    def test_no_auth_configured_treats_any_key_as_valid(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.post("/health/verify-key", json={"api_key": "anything"})
        body = resp.json()
        assert body["valid"] is True
        assert "No authentication configured" in body["message"]


class TestSetup:
    def test_creates_first_admin_key(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.post("/health/setup", json={"label": "Bootstrap"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "admin"
        assert body["label"] == "Bootstrap"
        assert len(body["api_key"]) == 64

    def test_rejected_when_already_configured(self, isolated_db):
        create_user_role("preexisting-key", "Lbl", "admin")
        with _client(isolated_db) as c:
            resp = c.post("/health/setup", json={"label": "X"})
        assert resp.status_code == 403


class TestReadiness:
    def test_unauthenticated_minimal_response(self, isolated_db):
        with _client(isolated_db) as c:
            resp = c.get("/health/readiness")
        # Unauthenticated callers always 200 with minimal body — no
        # component dict that could leak system topology.
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "components" not in body

    @pytest.mark.skip(
        reason="Authenticated readiness depends on Flask app context for ProcessManager + cli proxy; covered indirectly by Flask integration tests."
    )
    def test_authenticated_full_response(self, isolated_db):
        pass
