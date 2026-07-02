"""v0.6.1: migration 113 — rotated_from_token partial unique index."""

import pytest


def _index_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row is not None


class TestMigration113:
    def test_partial_unique_index_present(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            assert _index_exists(conn, "idx_sessions_rotated_from_token_unique")

    def test_index_is_partial(self, isolated_db):
        """Partial index — has WHERE clause; doesn't conflict with NULLs."""
        from app.database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = ?",
                ("idx_sessions_rotated_from_token_unique",),
            ).fetchone()
        assert row is not None
        sql = row[0].lower()
        assert "where" in sql and "not null" in sql

    def test_uniqueness_enforced_on_non_null_values(self, isolated_db):
        """Two rows with the same rotated_from_token should fail to insert."""
        from app.database import get_connection
        from app.db import errors
        from app.db.sessions import _generate_token, _get_unique_session_id
        from app.db.users import create_user

        # Make a user so the FK on sessions.user_id is satisfied.
        uid = create_user("uniq@test")
        with get_connection() as conn:
            id1 = _get_unique_session_id(conn)
            id2 = _get_unique_session_id(conn)
            conn.execute(
                "INSERT INTO sessions (id, token, user_id, expires_at, "
                "rotated_from_token) VALUES (?, ?, ?, ?, ?)",
                (id1, _generate_token(), uid, "2099-01-01", "shared-rotated-token"),
            )
            conn.commit()
            with pytest.raises(errors.IntegrityError):
                conn.execute(
                    "INSERT INTO sessions (id, token, user_id, expires_at, "
                    "rotated_from_token) VALUES (?, ?, ?, ?, ?)",
                    (id2, _generate_token(), uid, "2099-01-01", "shared-rotated-token"),
                )
                conn.commit()

    def test_null_values_do_not_conflict(self, isolated_db):
        """Multiple rows with NULL rotated_from_token must coexist
        (partial index excludes NULL)."""
        from app.database import get_connection
        from app.db.sessions import _generate_token, _get_unique_session_id
        from app.db.users import create_user

        uid = create_user("null@test")
        with get_connection() as conn:
            for _ in range(3):
                sid = _get_unique_session_id(conn)
                conn.execute(
                    "INSERT INTO sessions (id, token, user_id, expires_at) VALUES (?, ?, ?, ?)",
                    (sid, _generate_token(), uid, "2099-01-01"),
                )
            conn.commit()  # No IntegrityError

    def test_preflight_dedups_existing_duplicates(self, isolated_db, caplog):
        """Codex round-1 E: simulate a populated DB with duplicate
        rotated_from_token values, run migration 113 manually, and
        assert it dedups + warns instead of failing."""
        import logging

        from app.database import get_connection
        from app.db.migrations import _migrate_113_rotated_from_token_unique
        from app.db.sessions import _generate_token, _get_unique_session_id
        from app.db.users import create_user

        uid = create_user("dup@test")

        # Drop the unique index so we can plant a duplicate.
        with get_connection() as conn:
            conn.execute("DROP INDEX IF EXISTS idx_sessions_rotated_from_token_unique")
            conn.commit()
            id1 = _get_unique_session_id(conn)
            id2 = _get_unique_session_id(conn)
            shared = "duplicate-rotated-token-xyz"
            conn.execute(
                "INSERT INTO sessions (id, token, user_id, expires_at, "
                "rotated_from_token) VALUES (?, ?, ?, ?, ?)",
                (id1, _generate_token(), uid, "2099-01-01", shared),
            )
            conn.execute(
                "INSERT INTO sessions (id, token, user_id, expires_at, "
                "rotated_from_token) VALUES (?, ?, ?, ?, ?)",
                (id2, _generate_token(), uid, "2099-01-01", shared),
            )
            conn.commit()

        # Run migration 113 against the polluted DB.
        with caplog.at_level(logging.WARNING, logger="app.db.migrations"):
            with get_connection() as conn:
                _migrate_113_rotated_from_token_unique(conn)

        # Migration must succeed (no exception) and the dup must be
        # resolved: only one row keeps the rotated_from_token; the
        # other got nulled.
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, rotated_from_token FROM sessions WHERE id IN (?, ?) ORDER BY id",
                (id1, id2),
            ).fetchall()
        survivors = [r for r in rows if r[1] == shared]
        assert len(survivors) == 1
        nulled = [r for r in rows if r[1] is None]
        assert len(nulled) == 1
        # Codex round-2: assert the max-id-survivor contract documented
        # by the migration, not just the survivor count. Both ids are
        # auto-generated TEXT — lexicographic max corresponds to the
        # most recently inserted row given the timestamp prefix.
        assert survivors[0][0] == max(id1, id2)
        assert any("migration 113" in rec.message for rec in caplog.records)
