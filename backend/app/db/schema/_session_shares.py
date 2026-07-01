"""Session live-share tokens (Phase 25, 25-01 live-share).

One opaque-token table: a running ``ProjectSessionManager`` session is shared
by a cryptographically-random URL token (``secrets.token_urlsafe``) that is
scoped to ONE session, carries a ``read``|``chat`` scope, is REVOCABLE and
EXPIRING. The token IS the credential a tokenless teammate presents to attach
read-only (25-01) or co-drive (25-02) — it never grants operator/admin rights
and never leaks the operator's API key or session token.

Modules in ``schema/`` MUST NOT import each other; this exposes a single
``create_session_share_tables`` entry point called from ``create_fresh_schema``.
"""


def create_session_share_tables(conn):
    """Create ``session_share_tokens`` on a fresh database.

    Args:
        conn: An open sqlite3 connection.
    """
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
