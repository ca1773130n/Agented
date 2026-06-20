"""v0.5.12 migration 109 — session audit columns + session_events table."""


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


class TestMigration109:
    def test_sessions_has_rotated_from_token_column(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            assert _column_exists(conn, "sessions", "rotated_from_token")

    def test_sessions_has_revoked_at_column(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            assert _column_exists(conn, "sessions", "revoked_at")

    def test_sessions_has_revoke_reason_column(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            assert _column_exists(conn, "sessions", "revoke_reason")

    def test_session_events_table_exists(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='session_events'"
            ).fetchone()
            assert row is not None

    def test_session_events_has_expected_columns(self, isolated_db):
        from app.database import get_connection

        expected = {
            "id",
            "session_id",
            "user_id",
            "event_type",
            "occurred_at",
            "ip_address",
            "user_agent",
            "metadata",
        }
        with get_connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(session_events)").fetchall()}
        assert expected.issubset(cols)

    def test_session_events_indices_present(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            indices = {
                row[1]
                for row in conn.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='session_events'"
                ).fetchall()
            }
        assert "idx_session_events_session_id" in indices
        assert "idx_session_events_user_id" in indices
        assert "idx_session_events_occurred_at" in indices

    def test_sessions_rotated_from_token_index_present(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='sessions' "
                "AND name='idx_sessions_rotated_from_token'"
            ).fetchone()
            assert row is not None

    def test_migration_is_idempotent(self, isolated_db):
        """Re-running the migration must not raise — production safety."""
        from app.database import get_connection
        from app.db.migrations import _migrate_109_session_audit_columns

        with get_connection() as conn:
            _migrate_109_session_audit_columns(conn)
            _migrate_109_session_audit_columns(conn)
