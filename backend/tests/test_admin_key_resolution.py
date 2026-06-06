"""Admin-key resolution for sidecar auth must be deterministic.

When the first-operator backfill (#198) adds a second admin row, the
``SELECT api_key ... WHERE role='admin' LIMIT 1`` lookups used for sidecar
bearer auth must not nondeterministically pick a *different* key than the one
the sidecar's accounts are scoped under — otherwise the sidecar returns 0
accounts and the local backend_accounts mirror (and the onboarding tour's
account guard) goes empty. We pin the choice to the OLDEST admin key.
"""

from app.db.connection import get_connection
from app.db.ids import _get_unique_role_id


def _seed_admin(api_key: str, created_at: str):
    with get_connection() as conn:
        rid = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role, created_at) "
            "VALUES (?, ?, ?, 'admin', ?)",
            (rid, api_key, api_key, created_at),
        )
        conn.commit()


def test_resolve_admin_key_picks_oldest_when_multiple(isolated_db, monkeypatch):
    monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
    monkeypatch.delenv("AGENTED_API_KEY", raising=False)
    with get_connection() as conn:
        conn.execute("DELETE FROM user_roles")
        conn.commit()
    # Insert newest first to prove ordering (not insertion order) decides.
    _seed_admin("NEWKEY", "2026-06-01 00:00:00")
    _seed_admin("OLDKEY", "2026-01-01 00:00:00")

    from app.services.sidecar_account_sync_service import _resolve_admin_key

    assert _resolve_admin_key() == "OLDKEY"


def test_resolve_admin_key_env_override_wins(isolated_db, monkeypatch):
    monkeypatch.setenv("AI_ACCOUNTS_API_KEY", "ENVKEY")
    _seed_admin("DBKEY", "2026-01-01 00:00:00")

    from app.services.sidecar_account_sync_service import _resolve_admin_key

    assert _resolve_admin_key() == "ENVKEY"
