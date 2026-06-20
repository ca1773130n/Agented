"""Migration 171 — competitive-intelligence MVP schema (REQ-27).

Mirrors test_migration_170_iteration_confidence.py: with the isolated_db
fixture having run init_db, assert schema_version reaches 171 and the three
project-scoped tables exist with the documented columns + indexes. 166-170
must remain registered (the runner applies them in order, so 171 implies all
prior versions ran).
"""


def test_schema_version_is_171(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert max_version == 171


def test_migration_171_registered_after_170():
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: (name, func) for v, name, func in VERSIONED_MIGRATIONS}
    assert 170 in by_version, "baseline migration 170 must still be registered"
    assert 171 in by_version, "migration 171 must be registered"
    assert by_version[171][0] == "competitor_intel"


def test_three_tables_exist(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for table in ("competitor_source", "competitor_snapshot", "detected_signal"):
        assert table in names, f"{table} should exist after migration 171"


def test_competitor_source_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(competitor_source)")}
    expected = {
        "id",
        "project_id",
        "kind",
        "url",
        "origin",
        "etag",
        "watermark",
        "status",
        "label",
        "created_at",
    }
    assert expected <= cols, f"missing columns: {expected - cols}"


def test_competitor_snapshot_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(competitor_snapshot)")}
    assert {"id", "source_id", "fetched_at", "content_hash", "raw_ref"} <= cols


def test_detected_signal_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(detected_signal)")}
    assert {"id", "source_id", "summary", "signal_type", "score", "created_at"} <= cols


def test_indexes_exist(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        index_names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    for idx in (
        "idx_competitor_source_project",
        "idx_competitor_snapshot_source",
        "idx_detected_signal_source",
    ):
        assert idx in index_names, f"{idx} should exist after migration 171"


def test_optional_columns_accept_null(isolated_db):
    """etag/watermark/label are conditional cursors / display name — NULLable."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="CI null-column probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO competitor_source (id, project_id, kind, url) VALUES (?, ?, ?, ?)",
            ("cmps-nulls0", project_id, "product_url", "https://example.com"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT etag, watermark, label, origin, status "
            "FROM competitor_source WHERE id = ?",
            ("cmps-nulls0",),
        ).fetchone()
    # Optional cursors/label stay NULL; origin/status fall back to their defaults.
    assert row["etag"] is None
    assert row["watermark"] is None
    assert row["label"] is None
    assert row["origin"] == "manual"
    assert row["status"] == "active"
