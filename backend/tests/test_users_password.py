"""Tests for password hashing + auth (track B, wave 31)."""

from app.db.users import (
    authenticate,
    create_user,
    deactivate_user,
    hash_password,
    set_password,
    verify_password,
)


class TestHashAndVerify:
    def test_hash_returns_bcrypt_string(self):
        digest = hash_password("hunter2")
        assert digest.startswith("$2b$") or digest.startswith("$2a$")
        assert len(digest) >= 60

    def test_hash_is_salted_per_call(self):
        # Same plaintext, two hashes — must differ (per-call salt).
        a = hash_password("same-input")
        b = hash_password("same-input")
        assert a != b

    def test_verify_accepts_correct_password(self):
        digest = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", digest) is True

    def test_verify_rejects_wrong_password(self):
        digest = hash_password("real")
        assert verify_password("wrong", digest) is False

    def test_verify_handles_null_hash(self):
        assert verify_password("anything", None) is False

    def test_verify_handles_empty_hash(self):
        assert verify_password("anything", "") is False

    def test_verify_handles_garbage_hash(self):
        assert verify_password("x", "not-a-valid-bcrypt-string") is False


class TestSetPassword:
    def test_set_password_persists_hash(self, isolated_db):
        uid = create_user("setpw@example.com", "User")
        assert set_password(uid, "secret") is True

        from app.db.connection import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (uid,)
            ).fetchone()
        assert row[0] is not None
        assert verify_password("secret", row[0]) is True

    def test_set_password_returns_false_for_unknown_user(self, isolated_db):
        assert set_password("user-nope", "x") is False

    def test_set_password_rejects_empty(self, isolated_db):
        uid = create_user("empty@example.com")
        assert set_password(uid, "") is False


class TestAuthenticate:
    def test_authenticate_succeeds(self, isolated_db):
        uid = create_user("auth@example.com", "Auth")
        set_password(uid, "right")
        result = authenticate("auth@example.com", "right")
        assert result is not None
        assert result["id"] == uid
        assert "password_hash" not in result

    def test_authenticate_wrong_password(self, isolated_db):
        uid = create_user("wrongpw@example.com")
        set_password(uid, "real")
        assert authenticate("wrongpw@example.com", "fake") is None

    def test_authenticate_unknown_email(self, isolated_db):
        assert authenticate("nobody@example.com", "anything") is None

    def test_authenticate_inactive_user_blocked(self, isolated_db):
        uid = create_user("inactive@example.com")
        set_password(uid, "right")
        deactivate_user(uid)
        assert authenticate("inactive@example.com", "right") is None

    def test_authenticate_user_with_no_password_hash(self, isolated_db):
        # Legacy users (no password set) cannot authenticate even with empty
        # input — protects the legacy@local row from being hijacked.
        create_user("nopw@example.com")
        assert authenticate("nopw@example.com", "") is None
        assert authenticate("nopw@example.com", "guess") is None

    def test_authenticate_normalizes_email_case(self, isolated_db):
        uid = create_user("Case@Example.COM", "Case")
        set_password(uid, "x")
        assert authenticate("CASE@example.com", "x") is not None
