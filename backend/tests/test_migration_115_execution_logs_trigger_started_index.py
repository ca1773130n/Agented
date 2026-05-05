"""v0.7.0: migration 115 — composite (trigger_id, started_at) index.

Codex round-1 #2 on PR #46: the per-bot SLA query was running one
`WHERE trigger_id = ? AND started_at >= ?` per trigger with no
composite index, forcing SQLite to fall back to the started_at index
and re-filter trigger_id per row. Migration 115 adds the composite.
"""

from app.db.migrations import (
    _migrate_115_execution_logs_trigger_started_index,
)


def _index_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


class TestMigration115:
    def test_composite_index_present_after_migrations(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            assert _index_exists(conn, "idx_execution_logs_trigger_started")

    def test_index_is_on_execution_logs_table(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name=?",
                ("idx_execution_logs_trigger_started",),
            ).fetchone()
            assert row is not None
            assert row["tbl_name"] == "execution_logs"

    def test_index_columns_are_trigger_id_and_started_at(self, isolated_db):
        from app.database import get_connection

        with get_connection() as conn:
            cols = conn.execute("PRAGMA index_info(idx_execution_logs_trigger_started)").fetchall()
            names = [row["name"] for row in cols]
            assert names == ["trigger_id", "started_at"]

    def test_idempotent_rerun_does_not_raise(self, isolated_db):
        # IF NOT EXISTS guard — re-running the migration on an already
        # migrated DB is a no-op rather than an error.
        from app.database import get_connection

        with get_connection() as conn:
            _migrate_115_execution_logs_trigger_started_index(conn)
            _migrate_115_execution_logs_trigger_started_index(conn)
            assert _index_exists(conn, "idx_execution_logs_trigger_started")
