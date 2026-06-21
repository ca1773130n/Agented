"""Migration 174 — competitor_strategy schema (phase 26).

Mirrors test_migration_172_discovery_suggestion.py: with the isolated_db
fixture having run init_db, assert schema_version reaches 174 and the
project-scoped ``competitor_strategy`` table exists with the documented columns
(incl. legal_checklist + legal_cleared_at + plan_id) + index. 166-173 must
remain registered (the runner applies them in order, so 174 implies all prior
versions ran).
"""


def test_schema_version_is_174(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert max_version == 174


def test_migration_174_registered_after_173():
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: (name, func) for v, name, func in VERSIONED_MIGRATIONS}
    assert 173 in by_version, "baseline migration 173 must still be registered"
    assert 174 in by_version, "migration 174 must be registered"
    assert by_version[174][0] == "competitor_strategy"


def test_migrations_166_through_173_untouched():
    """The new migration appends — it must not displace any prior version."""
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: name for v, name, _ in VERSIONED_MIGRATIONS}
    assert by_version[166] == "projects_tesserae_distill"
    assert by_version[167] == "grd_plan_selections"
    assert by_version[168] == "grd_genome_suggestions"
    assert by_version[169] == "loop_iteration_cols"
    assert by_version[170] == "iteration_confidence"
    assert by_version[171] == "competitor_intel"
    assert by_version[172] == "discovery_suggestion"
    assert by_version[173] == "competitor_last_polled"


def test_competitor_strategy_table_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "competitor_strategy" in names, (
        "competitor_strategy should exist after migration 174"
    )


def test_competitor_strategy_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(competitor_strategy)")}
    expected = {
        "id",
        "project_id",
        "signal_ids",
        "title",
        "body",
        "backend_kind",
        "model",
        "status",
        "legal_checklist",
        "legal_cleared_at",
        "plan_id",
        "created_at",
        "updated_at",
    }
    assert expected <= cols, f"missing columns: {expected - cols}"


def test_status_defaults_to_proposed(isolated_db):
    """status defaults to 'proposed'; legal_checklist / legal_cleared_at / plan_id NULL."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="CS default probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO competitor_strategy (id, project_id) VALUES (?, ?)",
            ("cstr-defaults", project_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status, legal_checklist, legal_cleared_at, plan_id "
            "FROM competitor_strategy WHERE id = ?",
            ("cstr-defaults",),
        ).fetchone()
    assert row["status"] == "proposed"
    assert row["legal_checklist"] is None
    assert row["legal_cleared_at"] is None
    assert row["plan_id"] is None


def test_index_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        index_names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    assert "idx_competitor_strategy_project" in index_names, (
        "idx_competitor_strategy_project should exist after migration 174"
    )


def test_project_id_fk_cascade(isolated_db):
    """Deleting the project cascades to its strategies (ON DELETE CASCADE)."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="CS cascade probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO competitor_strategy (id, project_id) VALUES (?, ?)",
            ("cstr-cascade0", project_id),
        )
        conn.commit()
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM competitor_strategy WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
    assert remaining == 0, "strategies should be cascade-deleted with their project"
