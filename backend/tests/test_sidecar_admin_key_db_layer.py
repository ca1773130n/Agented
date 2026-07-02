"""The ai-accounts sidecar's fallback bearer auth must resolve admin keys
through the shared, DATABASE_URL-aware DB layer — so it works on BOTH SQLite
(the zero-config default) and Postgres (DEFER-26-01 / codex #5).

Before this fix, ``scripts/run_ai_accounts.py``'s ``LazyFlaskKeyAuth`` opened a
hard-coded ``backend/agented.db`` via ``sqlite3.connect`` directly. On a
Postgres deploy (``DATABASE_URL`` set, admin key seeded in Postgres
``user_roles``) that read returned an empty set, so ``/api/v1`` stayed
unauthorized even after the admin key was created. The read now goes through
``app.db.rbac.get_authorized_api_keys`` → ``get_connection`` → whichever backend
``config.DATABASE_URL`` selects.

``isolated_db`` runs each test on SQLite by default AND on Postgres when a
Postgres ``DATABASE_URL`` is configured (parametrized in conftest), so the SAME
helper is asserted against BOTH backends from one test body.
"""

import app.config as config
from app.db.connection import get_connection
from app.db.ids import _get_unique_role_id
from app.db.rbac import get_authorized_api_keys


def _seed(api_key: str, role: str = "admin"):
    with get_connection() as conn:
        rid = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, ?)",
            (rid, api_key, api_key, role),
        )
        conn.commit()


def _clear():
    with get_connection() as conn:
        conn.execute("DELETE FROM user_roles")
        conn.commit()


def test_resolves_seeded_admin_key(isolated_db):
    """Acceptance: a seeded admin key is found on the active backend."""
    _clear()
    _seed("ADMINKEY")
    assert "ADMINKEY" in get_authorized_api_keys()


def test_empty_when_no_keys(isolated_db):
    """Best-effort tolerance: no rows → empty set (sidecar 401s, not crashes)."""
    _clear()
    assert get_authorized_api_keys() == set()


def test_includes_all_keyed_roles(isolated_db):
    """Invariant — resolves exactly as today: ANY keyed role authenticates the
    sidecar bearer (the pre-fix SQLite query was ``WHERE api_key IS NOT NULL``,
    not role-scoped), so switching to the shared layer must not narrow the set."""
    _clear()
    _seed("ADMINKEY", role="admin")
    _seed("OPKEY", role="operator")
    keys = get_authorized_api_keys()
    assert {"ADMINKEY", "OPKEY"} <= keys


def test_sqlite_default_uses_config_db_path(isolated_db, monkeypatch):
    """SQLite default (DATABASE_URL unset): the helper reads config.DB_PATH — the
    same file the pre-fix hard-coded ``agented.db`` path resolved to in a real
    deploy — so the admin key resolves exactly as today. Skipped on the PG param
    (there DATABASE_URL is intentionally set)."""
    if config.DATABASE_URL:
        import pytest

        pytest.skip("SQLite-default assertion — not applicable on the Postgres param")
    monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
    _clear()
    _seed("SQLITEKEY")
    assert config.DATABASE_URL == ""  # unset ⇒ SQLite path
    assert "SQLITEKEY" in get_authorized_api_keys()
