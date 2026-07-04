"""Migration 176 — policies table (phase 23, 23-01 governance primitive).

Creates the ``policies`` table backing the stackable policy engine: a single
table holding rows at the SERVER / TEAM / SESSION scopes (scope + scope_id),
each carrying a ``kind`` (builtin name, filled in 23-02), an ``effect``
(allow/deny/ask), JSON ``params``, an ``enabled`` flag and a ``priority``.
``PolicyService.evaluate`` reads these rows session-first and short-circuits on
the first DENY. This test mirrors test_migration_175_* — assert the migration
is registered after 175, the table + both indexes exist, and re-applying is a
no-op (idempotent).
"""


def test_schema_version_is_176(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    # >= not ==: newer milestones add migrations past 176 (collab 177-179, etc.),
    # so this pins the floor (176 ran) without breaking every time the schema advances.
    assert max_version >= 176


def test_migration_176_registered_after_175():
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: (name, func) for v, name, func in VERSIONED_MIGRATIONS}
    assert 175 in by_version, "baseline migration 175 must still be registered"
    assert 176 in by_version, "migration 176 must be registered"
    assert by_version[176][0] == "policies"


def test_policies_table_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='policies'"
        ).fetchone()
    assert row is not None, "policies table should exist after migration 176"


def test_policies_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(policies)")}
    expected = {
        "id",
        "scope",
        "scope_id",
        "kind",
        "effect",
        "params",
        "enabled",
        "priority",
        "created_at",
        "updated_at",
    }
    assert expected <= cols, f"missing columns: {expected - cols}"


def test_policies_indexes_exist(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        idx = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='policies'"
            )
        }
    assert "idx_policies_scope" in idx
    assert "idx_policies_kind" in idx


def test_migration_176_idempotent(isolated_db):
    """Re-running the migration must not error or duplicate the table."""
    from app.db.connection import get_connection
    from app.db.migrations.v07_features import _migrate_176_policies

    with get_connection() as conn:
        # Insert a row, then re-apply the migration; the row must survive and
        # no error (table/index use IF NOT EXISTS).
        conn.execute(
            "INSERT INTO policies (id, scope, scope_id, kind, effect, params, "
            "enabled, priority, created_at, updated_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pol-idem01",
                "server",
                None,
                "noop",
                "allow",
                "{}",
                1,
                0,
                "2026-06-30T00:00:00Z",
                "2026-06-30T00:00:00Z",
            ),
        )
        conn.commit()
        _migrate_176_policies(conn)  # re-apply
        conn.commit()
        row = conn.execute(
            "SELECT id FROM policies WHERE id = ?", ("pol-idem01",)
        ).fetchone()
    assert row is not None, "row must survive an idempotent re-apply"
