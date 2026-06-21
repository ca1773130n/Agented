"""Migration 175 — competitor_strategy.session_id (phase 26, 26-05 wire).

Adds a nullable ``session_id TEXT`` to ``competitor_strategy`` — the forward-link
to the goal-loop the TRIPLE-GATED ``start_autoimplement`` seam launches. Mirrors
test_migration_173_competitor_last_polled's introspect-the-ALTER shape: assert
the migration is registered after 174, the column exists, and it defaults NULL
(the resting state for every strategy that never reaches the gated wired path).
"""


def test_schema_version_is_175(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert max_version == 175


def test_migration_175_registered_after_174():
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: (name, func) for v, name, func in VERSIONED_MIGRATIONS}
    assert 174 in by_version, "baseline migration 174 must still be registered"
    assert 175 in by_version, "migration 175 must be registered"
    assert by_version[175][0] == "competitor_strategy_session"


def test_session_id_column_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(competitor_strategy)")}
    assert "session_id" in cols, "session_id should exist after migration 175"


def test_session_id_defaults_to_null(isolated_db):
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="CS session default probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO competitor_strategy (id, project_id) VALUES (?, ?)",
            ("cstr-session0", project_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT session_id FROM competitor_strategy WHERE id = ?",
            ("cstr-session0",),
        ).fetchone()
    assert row["session_id"] is None
