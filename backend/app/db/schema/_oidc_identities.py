"""OIDC identity link table (Phase 25, 25-04 SSO).

Maps a verified ``(issuer, subject)`` from an OIDC provider to a local
``user_id`` so SSO is an ADDITIONAL way to reach the same session cookie — the
X-API-Key auth path is untouched. ``(issuer, subject)`` is the primary key: an
OIDC subject is stable per-issuer, so the pair uniquely identifies an external
identity and prevents two providers from colliding on a bare subject.
"""


def create_oidc_identity_tables(conn):
    """Create ``oidc_identities`` on a fresh database.

    Args:
        conn: An open sqlite3 connection.
    """
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oidc_identities_user ON oidc_identities(user_id)")
