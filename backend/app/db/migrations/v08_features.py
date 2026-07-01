"""Migrations for the v0.8.0 track — Phase 25 real-time multi-user collaboration.

Hosts v177+ migrations for live-share / co-drive / session-fork / OIDC SSO.
Bucket files do not import each other; this appends onto the canonical
``VERSIONED_MIGRATIONS`` registry assembled in ``migrations/__init__``.

  - 177 session_share_tokens  — scoped, revocable, expiring live-share tokens (25-01)
  - 178 project_session_owner — ``created_by`` column so a shared session has an
                                owner to gate ``stream_project_session`` against (25-01)
  - 179 oidc_identities       — (issuer, subject) → user link for OIDC SSO (25-04)
                                (appended by 25-04)
"""


def _column_exists(conn, table: str, column: str) -> bool:
    """True if ``table`` already has ``column`` (defensive ALTER guard)."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any((r[1] if not isinstance(r, dict) else r["name"]) == column for r in rows)


def _migrate_177_session_share_tokens(conn):
    """Live-share token table (25-01). Mirrors schema/_session_shares.py DDL."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_share_tokens (
            token TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_share_tokens_session "
        "ON session_share_tokens(session_id)"
    )


def _migrate_178_project_session_owner(conn):
    """Add ``project_sessions.created_by`` so a session has an owner to gate on (25-01).

    Legacy/autonomous sessions leave this NULL (unattributed) and remain
    streamable for backward compatibility; only a session with a non-NULL owner
    is owner-gated on ``stream_project_session``.
    """
    if not _column_exists(conn, "project_sessions", "created_by"):
        conn.execute("ALTER TABLE project_sessions ADD COLUMN created_by TEXT")


def _migrate_179_oidc_identities(conn):
    """OIDC (issuer, subject) → user link table (25-04). Mirrors
    schema/_oidc_identities.py DDL."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS oidc_identities (
            provider TEXT NOT NULL,
            issuer TEXT NOT NULL,
            subject TEXT NOT NULL,
            user_id TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP NOT NULL,
            PRIMARY KEY (issuer, subject)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_oidc_identities_user ON oidc_identities(user_id)"
    )


V08_MIGRATIONS = [
    (177, "session_share_tokens", _migrate_177_session_share_tokens),
    (178, "project_session_owner", _migrate_178_project_session_owner),
    (179, "oidc_identities", _migrate_179_oidc_identities),
]
