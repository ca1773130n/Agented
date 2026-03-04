"""Comprehensive tests for the secrets vault.

Tests Fernet encryption, MultiFernet key rotation, CRUD API endpoints,
audit logging, performance, and execution service integration.
"""

import os
import time
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.services.secret_vault_service import SecretVaultService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def vault_key(monkeypatch):
    """Set up a vault encryption key for every test."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGENTED_VAULT_KEYS", key)
    SecretVaultService.reset()
    yield key
    SecretVaultService.reset()


# ---------------------------------------------------------------------------
# Fernet encrypt/decrypt roundtrip
# ---------------------------------------------------------------------------


class TestFernetRoundtrip:
    """Test basic encryption and decryption."""

    def test_roundtrip_basic(self):
        """Encrypt then decrypt produces identical plaintext."""
        ct = SecretVaultService.encrypt("my-api-key-123")
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == "my-api-key-123"

    def test_roundtrip_unicode(self):
        """Unicode strings survive encrypt/decrypt."""
        secret = "token-with-unicode-\u00e9\u00e0\u00fc"
        ct = SecretVaultService.encrypt(secret)
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == secret

    def test_roundtrip_empty_string(self):
        """Empty strings can be encrypted/decrypted."""
        ct = SecretVaultService.encrypt("")
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == ""

    def test_roundtrip_long_value(self):
        """Long values survive encrypt/decrypt."""
        secret = "x" * 10000
        ct = SecretVaultService.encrypt(secret)
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == secret

    def test_performance_under_10ms(self):
        """Encryption and decryption each complete in under 10ms."""
        plaintext = "performance-test-secret-value-12345"

        start = time.perf_counter()
        ct = SecretVaultService.encrypt(plaintext)
        encrypt_time = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        SecretVaultService.decrypt(ct, purpose="perf", accessor="test")
        decrypt_time = (time.perf_counter() - start) * 1000

        assert encrypt_time < 10, f"Encrypt took {encrypt_time:.2f}ms (limit: 10ms)"
        assert decrypt_time < 10, f"Decrypt took {decrypt_time:.2f}ms (limit: 10ms)"


# ---------------------------------------------------------------------------
# MultiFernet key rotation
# ---------------------------------------------------------------------------


class TestKeyRotation:
    """Test MultiFernet key rotation support."""

    def test_decrypt_with_rotated_key(self, monkeypatch):
        """Secrets encrypted with old key are decryptable after adding new primary key."""
        key_a = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENTED_VAULT_KEYS", key_a)
        SecretVaultService.reset()

        ct = SecretVaultService.encrypt("old-secret")

        # Add new key B as primary (B,A)
        key_b = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENTED_VAULT_KEYS", f"{key_b},{key_a}")
        SecretVaultService.reset()

        # Old ciphertext still decryptable
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == "old-secret"

    def test_new_encryption_uses_primary(self, monkeypatch):
        """New encryptions use the first (primary) key."""
        key_a = Fernet.generate_key().decode()
        key_b = Fernet.generate_key().decode()
        monkeypatch.setenv("AGENTED_VAULT_KEYS", f"{key_b},{key_a}")
        SecretVaultService.reset()

        ct = SecretVaultService.encrypt("new-secret")

        # Decrypt with only key_b (the primary) should work
        monkeypatch.setenv("AGENTED_VAULT_KEYS", key_b)
        SecretVaultService.reset()
        pt = SecretVaultService.decrypt(ct, purpose="test", accessor="test")
        assert pt == "new-secret"


# ---------------------------------------------------------------------------
# Vault unconfigured
# ---------------------------------------------------------------------------


class TestVaultUnconfigured:
    """Test behavior when vault is not configured."""

    def test_is_configured_false(self, monkeypatch):
        """is_configured() returns False when env var is missing."""
        monkeypatch.delenv("AGENTED_VAULT_KEYS", raising=False)
        SecretVaultService.reset()
        assert SecretVaultService.is_configured() is False

    def test_encrypt_raises_runtime_error(self, monkeypatch):
        """encrypt() raises RuntimeError when keys not set."""
        monkeypatch.delenv("AGENTED_VAULT_KEYS", raising=False)
        SecretVaultService.reset()
        with pytest.raises(RuntimeError, match="AGENTED_VAULT_KEYS not configured"):
            SecretVaultService.encrypt("test")


# ---------------------------------------------------------------------------
# Secret CRUD via service
# ---------------------------------------------------------------------------


class TestSecretCRUD:
    """Test secret create, read, update, delete via SecretVaultService."""

    def test_create_and_get(self, isolated_db):
        """Create a secret and retrieve its value."""
        sid = SecretVaultService.create_secret(
            name="test-api-key", value="sk-12345", description="Test key"
        )
        assert sid.startswith("sec-")

        value = SecretVaultService.get_secret_value(sid, accessor="test")
        assert value == "sk-12345"

    def test_get_by_name(self, isolated_db):
        """Retrieve secret by name."""
        SecretVaultService.create_secret(name="my-token", value="tok-abc")
        value = SecretVaultService.get_secret_value("my-token", accessor="test")
        assert value == "tok-abc"

    def test_update_value(self, isolated_db):
        """Update a secret's value."""
        sid = SecretVaultService.create_secret(name="rotate-me", value="old-val")
        SecretVaultService.update_secret(sid, value="new-val")
        value = SecretVaultService.get_secret_value(sid, accessor="test")
        assert value == "new-val"

    def test_update_description(self, isolated_db):
        """Update a secret's description."""
        sid = SecretVaultService.create_secret(name="desc-test", value="val", description="old")
        SecretVaultService.update_secret(sid, description="new desc")

        from app.db.secrets import get_secret
        secret = get_secret(sid)
        assert secret["description"] == "new desc"

    def test_delete(self, isolated_db):
        """Delete a secret."""
        sid = SecretVaultService.create_secret(name="delete-me", value="val")
        assert SecretVaultService.delete_secret(sid) is True
        assert SecretVaultService.get_secret_value(sid, accessor="test") is None

    def test_delete_nonexistent(self, isolated_db):
        """Deleting a nonexistent secret returns False."""
        assert SecretVaultService.delete_secret("sec-nonexistent") is False

    def test_list_never_returns_encrypted_value(self, isolated_db):
        """list_secrets() NEVER includes the encrypted_value field."""
        SecretVaultService.create_secret(name="list-test", value="secret-val")
        from app.db.secrets import list_secrets
        secrets = list_secrets()
        assert len(secrets) >= 1
        for s in secrets:
            assert "encrypted_value" not in s


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


class TestAuditLogging:
    """Test that secret operations produce audit log entries."""

    def test_decrypt_logs_access(self, isolated_db):
        """Decrypting a secret logs an audit event."""
        from app.services.audit_log_service import _recent_events

        initial_count = len(_recent_events)
        ct = SecretVaultService.encrypt("test")
        SecretVaultService.decrypt(ct, purpose="audit-test", accessor="tester")

        # Should have at least one new audit event
        new_events = list(_recent_events)[initial_count:]
        access_events = [e for e in new_events if e["action"] == "secret.access"]
        assert len(access_events) >= 1
        assert access_events[0]["details"]["accessor"] == "tester"

    def test_reveal_logs_access(self, isolated_db):
        """Revealing a secret via get_secret_value logs audit events."""
        from app.services.audit_log_service import _recent_events

        sid = SecretVaultService.create_secret(name="reveal-audit", value="val")
        initial_count = len(_recent_events)

        SecretVaultService.get_secret_value(sid, accessor="api-user")

        new_events = list(_recent_events)[initial_count:]
        access_events = [e for e in new_events if e["action"] == "secret.access"]
        assert len(access_events) >= 1

    def test_update_logs_field_changes(self, isolated_db):
        """update_secret() calls log_field_changes with before/after metadata."""
        from app.services.audit_log_service import _recent_events

        sid = SecretVaultService.create_secret(
            name="update-audit", value="val", description="old desc"
        )
        initial_count = len(_recent_events)

        SecretVaultService.update_secret(sid, description="new desc")

        new_events = list(_recent_events)[initial_count:]
        update_events = [e for e in new_events if e["action"] == "secret.update"]
        assert len(update_events) >= 1
        changes = update_events[0]["details"]["changes"]
        assert "description" in changes
        assert changes["description"]["old"] == "old desc"
        assert changes["description"]["new"] == "new desc"

    def test_update_value_logs_rotation(self, isolated_db):
        """Updating a secret's value logs a value_rotated event."""
        from app.services.audit_log_service import _recent_events

        sid = SecretVaultService.create_secret(name="rotate-audit", value="old")
        initial_count = len(_recent_events)

        SecretVaultService.update_secret(sid, value="new")

        new_events = list(_recent_events)[initial_count:]
        rotate_events = [e for e in new_events if e["action"] == "secret.value_rotated"]
        assert len(rotate_events) >= 1

    def test_delete_logs_field_changes(self, isolated_db):
        """delete_secret() calls log_field_changes with before state."""
        from app.services.audit_log_service import _recent_events

        sid = SecretVaultService.create_secret(name="delete-audit", value="val")
        initial_count = len(_recent_events)

        SecretVaultService.delete_secret(sid)

        new_events = list(_recent_events)[initial_count:]
        delete_events = [e for e in new_events if e["action"] == "secret.delete"]
        assert len(delete_events) >= 1
        changes = delete_events[0]["details"]["changes"]
        assert "name" in changes
        assert changes["name"]["old"] == "delete-audit"
        assert changes["name"]["new"] is None


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestSecretsAPI:
    """Test secrets API endpoints."""

    def test_create_secret_api(self, client, isolated_db):
        """POST /admin/secrets creates a secret and returns metadata."""
        resp = client.post(
            "/admin/secrets/",
            json={"name": "api-test", "value": "secret-val", "description": "test"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "api-test"
        assert data["id"].startswith("sec-")
        # NEVER returns value or encrypted_value
        assert "value" not in data
        assert "encrypted_value" not in data

    def test_list_secrets_api(self, client, isolated_db):
        """GET /admin/secrets returns metadata only."""
        client.post("/admin/secrets/", json={"name": "list-1", "value": "v1"})
        client.post("/admin/secrets/", json={"name": "list-2", "value": "v2"})

        resp = client.get("/admin/secrets/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["secrets"]) >= 2
        for s in data["secrets"]:
            assert "encrypted_value" not in s
            assert "value" not in s

    def test_get_secret_detail_api(self, client, isolated_db):
        """GET /admin/secrets/<id> returns metadata without value."""
        create_resp = client.post("/admin/secrets/", json={"name": "detail-test", "value": "v"})
        sid = create_resp.get_json()["id"]

        resp = client.get(f"/admin/secrets/{sid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "detail-test"
        assert "value" not in data
        assert "encrypted_value" not in data

    def test_reveal_secret_api(self, client, isolated_db):
        """POST /admin/secrets/<id>/reveal returns decrypted value."""
        create_resp = client.post("/admin/secrets/", json={"name": "reveal-test", "value": "my-key"})
        sid = create_resp.get_json()["id"]

        resp = client.post(f"/admin/secrets/{sid}/reveal")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["value"] == "my-key"

    def test_update_secret_api(self, client, isolated_db):
        """PUT /admin/secrets/<id> updates value and description."""
        create_resp = client.post(
            "/admin/secrets/", json={"name": "update-test", "value": "old", "description": "old"}
        )
        sid = create_resp.get_json()["id"]

        resp = client.put(f"/admin/secrets/{sid}", json={"value": "new", "description": "updated"})
        assert resp.status_code == 200

        # Verify the new value
        reveal = client.post(f"/admin/secrets/{sid}/reveal")
        assert reveal.get_json()["value"] == "new"

    def test_delete_secret_api(self, client, isolated_db):
        """DELETE /admin/secrets/<id> removes the secret."""
        create_resp = client.post("/admin/secrets/", json={"name": "del-test", "value": "v"})
        sid = create_resp.get_json()["id"]

        resp = client.delete(f"/admin/secrets/{sid}")
        assert resp.status_code == 200

        resp = client.get(f"/admin/secrets/{sid}")
        assert resp.status_code == 404

    def test_vault_status_api(self, client, isolated_db):
        """GET /admin/secrets/status returns vault status."""
        resp = client.get("/admin/secrets/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["configured"] is True

    def test_vault_unconfigured_returns_503(self, client, isolated_db, monkeypatch):
        """API returns 503 when vault keys not configured."""
        monkeypatch.delenv("AGENTED_VAULT_KEYS", raising=False)
        SecretVaultService.reset()

        resp = client.post("/admin/secrets/", json={"name": "fail", "value": "v"})
        assert resp.status_code == 503

    def test_create_duplicate_name(self, client, isolated_db):
        """Creating a secret with a duplicate name returns 409."""
        client.post("/admin/secrets/", json={"name": "dupe", "value": "v1"})
        resp = client.post("/admin/secrets/", json={"name": "dupe", "value": "v2"})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# get_secrets_for_execution
# ---------------------------------------------------------------------------


class TestGetSecretsForExecution:
    """Test the execution env var injection helper."""

    def test_returns_prefixed_env_dict(self, isolated_db):
        """get_secrets_for_execution returns AGENTED_SECRET_ prefixed keys."""
        SecretVaultService.create_secret(name="slack_token", value="xoxb-123")
        SecretVaultService.create_secret(name="jira_key", value="JIRA-456")

        env = SecretVaultService.get_secrets_for_execution(scope="global")
        assert "AGENTED_SECRET_SLACK_TOKEN" in env
        assert env["AGENTED_SECRET_SLACK_TOKEN"] == "xoxb-123"
        assert "AGENTED_SECRET_JIRA_KEY" in env
        assert env["AGENTED_SECRET_JIRA_KEY"] == "JIRA-456"

    def test_scoped_secrets(self, isolated_db):
        """Only secrets matching the requested scope are returned."""
        SecretVaultService.create_secret(name="global_key", value="g", scope="global")
        SecretVaultService.create_secret(name="project_key", value="p", scope="project")

        env = SecretVaultService.get_secrets_for_execution(scope="project")
        assert "AGENTED_SECRET_PROJECT_KEY" in env
        assert "AGENTED_SECRET_GLOBAL_KEY" not in env

    def test_empty_when_no_secrets(self, isolated_db):
        """Returns empty dict when no secrets exist."""
        env = SecretVaultService.get_secrets_for_execution()
        assert env == {}
