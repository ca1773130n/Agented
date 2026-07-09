"""First-operator-admin bootstrap.

A self-hosted install with no human admin would lock the operator out of
/admin/* (the bootstrap API-key admin row has an empty user_id and can't be
resolved from a session login). These cover the two closes for that gap:
``ensure_user_admin`` on signup, and ``backfill_bootstrap_admin`` on startup.
"""

from litestar.testing import create_test_client

from app.db.connection import get_connection
from app.db.ids import _get_unique_role_id
from app.db.rbac import (
    backfill_bootstrap_admin,
    ensure_user_admin,
    generate_api_key,
    get_admin_api_key,
    get_highest_role_for_user,
    registration_open,
    user_bound_admin_exists,
)
from app.db.users import create_user, set_password
from app_litestar.auth import provide_caller
from app_litestar.routes.auth import auth_router
from app_litestar.routes.health import health_router
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[health_router, rbac_router, auth_router],
        dependencies={"caller": provide_caller},
    )


def _seed_orphan_apikey_admin():
    """Mimic the health.py bootstrap: an admin role on an API key with a NULL
    user_id (the column is omitted there) — the row that exists today yet
    locks out session logins."""
    with get_connection() as conn:
        role_id = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, ?)",
            (role_id, generate_api_key(), "orphan", "admin"),
        )
        conn.commit()


class TestEnsureUserAdmin:
    def test_grants_first_operator_then_resolves_as_admin(self, isolated_db):
        assert user_bound_admin_exists() is False
        uid = create_user("op1@example.com")
        set_password(uid, "supersecret")

        assert ensure_user_admin(uid) is True
        assert get_highest_role_for_user(uid) == "admin"
        assert user_bound_admin_exists() is True

    def test_noop_once_a_user_holds_admin(self, isolated_db):
        u1 = create_user("op1@example.com")
        set_password(u1, "supersecret")
        assert ensure_user_admin(u1) is True

        u2 = create_user("op2@example.com")
        set_password(u2, "supersecret")
        assert ensure_user_admin(u2) is False
        assert get_highest_role_for_user(u2) is None

    def test_orphan_apikey_admin_does_not_count_as_user_admin(self, isolated_db):
        _seed_orphan_apikey_admin()
        # The orphan (empty user_id) must NOT satisfy the bootstrap check —
        # otherwise the operator stays locked out.
        assert user_bound_admin_exists() is False
        uid = create_user("op1@example.com")
        set_password(uid, "supersecret")
        assert ensure_user_admin(uid) is True
        assert get_highest_role_for_user(uid) == "admin"

    def test_empty_user_id_is_rejected(self, isolated_db):
        assert ensure_user_admin("") is False


class TestBackfillBootstrapAdmin:
    def test_promotes_earliest_real_login_skipping_passwordless(self, isolated_db):
        # Synthetic, passwordless account created first (like legacy@local).
        legacy = create_user("legacy@local")
        # Real operator with a password, created after.
        real = create_user("op@example.com")
        set_password(real, "supersecret")

        promoted = backfill_bootstrap_admin()
        assert promoted == real
        assert get_highest_role_for_user(real) == "admin"
        assert get_highest_role_for_user(legacy) is None

    def test_noop_when_a_user_already_admin(self, isolated_db):
        u1 = create_user("op1@example.com")
        set_password(u1, "supersecret")
        assert ensure_user_admin(u1) is True

        u2 = create_user("op2@example.com")
        set_password(u2, "supersecret")
        assert backfill_bootstrap_admin() is None

    def test_noop_when_no_real_login_exists(self, isolated_db):
        # Only a passwordless synthetic account — nothing safe to promote.
        create_user("legacy@local")
        assert backfill_bootstrap_admin() is None


class TestSignupGrantsFirstOperatorAdmin:
    def test_first_signup_is_admin_second_is_not(self, isolated_db):
        with _client(isolated_db) as ls:
            r1 = ls.post(
                "/api/auth/signup",
                json={"email": "first@example.com", "password": "supersecret", "display_name": ""},
            )
            assert r1.status_code == 201
            uid1 = r1.json()["user"]["id"]

            r2 = ls.post(
                "/api/auth/signup",
                json={"email": "second@example.com", "password": "supersecret", "display_name": ""},
            )
            assert r2.status_code == 201
            uid2 = r2.json()["user"]["id"]

        assert get_highest_role_for_user(uid1) == "admin"
        assert get_highest_role_for_user(uid2) is None

    def test_first_signup_returns_admin_api_key_second_does_not(self, isolated_db):
        # Onboarding relies on the first-admin signup surfacing its minted API
        # key (stored, previously never returned) so the SPA can use it as
        # X-API-Key AND as the ai-accounts sidecar bearer for discovery.
        with _client(isolated_db) as ls:
            r1 = ls.post(
                "/api/auth/signup",
                json={"email": "first@example.com", "password": "supersecret", "display_name": ""},
            )
            assert r1.status_code == 201
            body1 = r1.json()
            uid1 = body1["user"]["id"]
            # The returned key must match the row ensure_user_admin persisted —
            # i.e. it is a real user_roles key the sidecar will accept.
            assert body1.get("api_key")
            assert body1["api_key"] == get_admin_api_key(uid1)

            r2 = ls.post(
                "/api/auth/signup",
                json={"email": "second@example.com", "password": "supersecret", "display_name": ""},
            )
            assert r2.status_code == 201
            # Second (non-admin) signup grants no admin, so no key is surfaced.
            assert "api_key" not in r2.json()


class TestRegistrationGate:
    def test_open_by_default(self, isolated_db):
        assert registration_open() is True
        with _client(isolated_db) as ls:
            r = ls.post(
                "/api/auth/signup",
                json={"email": "a@b.com", "password": "supersecret", "display_name": ""},
            )
            assert r.status_code == 201

    def test_disable_flag_closes_signup(self, isolated_db, monkeypatch):
        monkeypatch.setenv("AGENTED_DISABLE_SIGNUP", "1")
        assert registration_open() is False
        with _client(isolated_db) as ls:
            r = ls.post(
                "/api/auth/signup",
                json={"email": "a@b.com", "password": "supersecret", "display_name": ""},
            )
            assert r.status_code == 403

    def test_disable_flag_accepts_truthy_variants(self, isolated_db, monkeypatch):
        for val in ("1", "true", "YES", "on"):
            monkeypatch.setenv("AGENTED_DISABLE_SIGNUP", val)
            assert registration_open() is False
        monkeypatch.setenv("AGENTED_DISABLE_SIGNUP", "0")
        assert registration_open() is True
