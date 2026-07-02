"""OIDC SSO — subject mapping, signup-gate, callback, and API-key regression (25-04)."""

from types import SimpleNamespace

import pytest
from litestar.exceptions import PermissionDeniedException
from litestar.response import Redirect

from app.db.oidc_identities import get_user_for_identity, link_identity
from app.db.users import create_user, get_user
from app.services.oidc_service import OidcError, OidcService
from app_litestar.routes.oidc import _STATE_COOKIE, oidc_callback

ISS = "https://accounts.example.com"


# ---------------------------------------------------------------------------
# map_subject_to_user — signup-gate + takeover guard (locked #6)
# ---------------------------------------------------------------------------


class TestMapSubjectToUser:
    def test_existing_linked_identity_returns_user(self, isolated_db):
        uid = create_user("alice@example.com")
        link_identity("google", ISS, "sub-123", uid, "alice@example.com")
        assert OidcService.map_subject_to_user(ISS, "sub-123", "alice@example.com") == uid

    def test_open_signup_unknown_identity_creates_and_links(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AGENTED_DISABLE_SIGNUP", raising=False)
        uid = OidcService.map_subject_to_user(ISS, "sub-new", "bob@example.com", provider="google")
        assert uid
        assert get_user(uid)["email"] == "bob@example.com"
        # The identity is now linked → a second call returns the SAME user.
        assert get_user_for_identity(ISS, "sub-new") == uid
        assert OidcService.map_subject_to_user(ISS, "sub-new", "bob@example.com") == uid

    def test_closed_signup_unlinked_identity_denied(self, isolated_db, monkeypatch):
        monkeypatch.setenv("AGENTED_DISABLE_SIGNUP", "1")
        with pytest.raises(OidcError):
            OidcService.map_subject_to_user(ISS, "sub-x", "eve@example.com")

    def test_closed_signup_linked_identity_allowed(self, isolated_db, monkeypatch):
        uid = create_user("carol@example.com")
        link_identity("google", ISS, "sub-c", uid, "carol@example.com")
        monkeypatch.setenv("AGENTED_DISABLE_SIGNUP", "1")
        assert OidcService.map_subject_to_user(ISS, "sub-c", "carol@example.com") == uid

    def test_unverified_email_does_not_hijack_existing_user(self, isolated_db, monkeypatch):
        monkeypatch.delenv("AGENTED_DISABLE_SIGNUP", raising=False)
        victim = create_user("victim@example.com")
        # An attacker's IdP asserts the victim's email but WITHOUT email_verified.
        uid = OidcService.map_subject_to_user(
            ISS, "attacker-sub", "victim@example.com", email_verified=False
        )
        # A fresh, distinct user is created — the victim's account is NOT taken over.
        assert uid != victim


# ---------------------------------------------------------------------------
# configured_providers — graceful-without-key
# ---------------------------------------------------------------------------


class TestConfiguredProviders:
    def test_empty_without_env(self, isolated_db, monkeypatch):
        for var in list(__import__("os").environ):
            if var.startswith("OIDC_"):
                monkeypatch.delenv(var, raising=False)
        assert OidcService.configured_providers() == []

    def test_provider_offered_when_configured(self, isolated_db, monkeypatch):
        monkeypatch.setenv("OIDC_GOOGLE_CLIENT_ID", "cid")
        monkeypatch.setenv("OIDC_GOOGLE_CLIENT_SECRET", "secret")
        assert "google" in OidcService.configured_providers()


# ---------------------------------------------------------------------------
# callback — mocked exchange mints a session; state mismatch → 403
# ---------------------------------------------------------------------------


def _request(state_q, code, state_cookie):
    return SimpleNamespace(
        query_params=SimpleNamespace(
            get=lambda k, d=None: {"state": state_q, "code": code}.get(k, d)
        ),
        cookies={_STATE_COOKIE: state_cookie} if state_cookie else {},
        url=SimpleNamespace(scheme="http", netloc="localhost"),
        headers=SimpleNamespace(get=lambda k, d=None: "localhost" if k == "host" else d),
    )


def _configure_google(monkeypatch):
    monkeypatch.setenv("OIDC_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("OIDC_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.delenv("AGENTED_DISABLE_SIGNUP", raising=False)


def test_callback_mints_session_and_redirects(isolated_db, monkeypatch):
    _configure_google(monkeypatch)
    monkeypatch.setattr(
        OidcService,
        "exchange_code",
        classmethod(
            lambda cls, provider, code, redirect_uri, nonce=None: {
                "sub": "sub-cb",
                "iss": "https://accounts.google.com",
                "email": "dave@example.com",
                "email_verified": True,
            }
        ),
    )
    resp = oidc_callback.fn("google", _request("state1", "code1", "state1:nonce1"))
    assert isinstance(resp, Redirect)
    # A session cookie was set on the redirect.
    cookie_keys = {c.key for c in (resp.cookies or [])}
    assert "agented_session" in cookie_keys
    # A user was created + linked for the verified subject.
    assert get_user_for_identity("https://accounts.google.com", "sub-cb")


def test_callback_state_mismatch_403(isolated_db, monkeypatch):
    _configure_google(monkeypatch)
    with pytest.raises(PermissionDeniedException):
        oidc_callback.fn("google", _request("attacker", "code1", "real-state:nonce1"))


def test_callback_missing_state_cookie_403(isolated_db, monkeypatch):
    _configure_google(monkeypatch)
    with pytest.raises(PermissionDeniedException):
        oidc_callback.fn("google", _request("state1", "code1", None))


# ---------------------------------------------------------------------------
# regression: X-API-Key path unchanged with OIDC routes mounted (criterion #4)
# ---------------------------------------------------------------------------


def test_api_key_path_unchanged_with_oidc_mounted(isolated_db):
    from litestar.testing import TestClient

    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key, invalidate_key_cache
    from app_litestar.main import create_app

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES ('u-admin', 'admin@test', 'x', CURRENT_TIMESTAMP)"
        )
        conn.commit()
    api_key = generate_api_key()
    assert create_user_role(api_key, label="t", role="admin", user_id="u-admin") is not None
    invalidate_key_cache()

    with TestClient(app=create_app()) as client:
        # OIDC routes are mounted; an X-API-Key request still authenticates
        # (i.e. the middleware does NOT reject it as unauthorized).
        resp = client.get("/api/products", headers={"X-API-Key": api_key})
    assert resp.status_code != 401
