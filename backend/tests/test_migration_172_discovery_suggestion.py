"""Migration 172 — discovery_suggestion queue schema (phase 24).

Mirrors test_migration_171_competitor_intel.py: with the isolated_db fixture
having run init_db, assert schema_version reaches 172 and the project-scoped
``discovery_suggestion`` table exists with the documented columns + index +
UNIQUE(project_id, candidate_owner, candidate_repo). 166-171 must remain
registered (the runner applies them in order, so 172 implies all prior
versions ran).
"""

import pytest

from app.db import errors


def test_schema_version_is_172(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    # >= not ==: newer milestones add migrations past 172, so pin the floor
    # (172 ran) instead of breaking every time the schema advances.
    assert max_version >= 172


def test_migration_172_registered_after_171():
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: (name, func) for v, name, func in VERSIONED_MIGRATIONS}
    assert 171 in by_version, "baseline migration 171 must still be registered"
    assert 172 in by_version, "migration 172 must be registered"
    assert by_version[172][0] == "discovery_suggestion"


def test_migrations_166_through_171_untouched():
    """The new migration appends — it must not displace any prior version."""
    from app.db.migrations import VERSIONED_MIGRATIONS

    by_version = {v: name for v, name, _ in VERSIONED_MIGRATIONS}
    assert by_version[166] == "projects_tesserae_distill"
    assert by_version[167] == "grd_plan_selections"
    assert by_version[168] == "grd_genome_suggestions"
    assert by_version[169] == "loop_iteration_cols"
    assert by_version[170] == "iteration_confidence"
    assert by_version[171] == "competitor_intel"


def test_discovery_suggestion_table_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "discovery_suggestion" in names, "discovery_suggestion should exist after migration 172"


def test_discovery_suggestion_columns(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(discovery_suggestion)")}
    expected = {
        "id",
        "project_id",
        "candidate_owner",
        "candidate_repo",
        "candidate_url",
        "kind",
        "score",
        "reason",
        "evidence",
        "status",
        "source_id",
        "created_at",
        "updated_at",
    }
    assert expected <= cols, f"missing columns: {expected - cols}"


def test_status_defaults_to_suggested(isolated_db):
    """status defaults to 'suggested' and kind to 'github_repo'; score NULLable."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="DS default probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO discovery_suggestion "
            "(id, project_id, candidate_owner, candidate_repo, candidate_url) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dsug-defaults", project_id, "acme", "widget", "https://github.com/acme/widget"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status, kind, score FROM discovery_suggestion WHERE id = ?",
            ("dsug-defaults",),
        ).fetchone()
    assert row["status"] == "suggested"
    assert row["kind"] == "github_repo"
    assert row["score"] is None


def test_index_exists(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        index_names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    assert "idx_discovery_suggestion_project" in index_names, (
        "idx_discovery_suggestion_project should exist after migration 172"
    )


def test_unique_project_owner_repo_constraint(isolated_db):
    """A duplicate (project_id, candidate_owner, candidate_repo) raises IntegrityError."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="DS unique probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO discovery_suggestion "
            "(id, project_id, candidate_owner, candidate_repo, candidate_url) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dsug-uniq001", project_id, "acme", "widget", "https://github.com/acme/widget"),
        )
        conn.commit()
        with pytest.raises(errors.IntegrityError):
            conn.execute(
                "INSERT INTO discovery_suggestion "
                "(id, project_id, candidate_owner, candidate_repo, candidate_url) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "dsug-uniq002",
                    project_id,
                    "acme",
                    "widget",
                    "https://github.com/acme/widget",
                ),
            )


def test_project_id_fk_cascade(isolated_db):
    """Deleting the project cascades to its discovery suggestions (ON DELETE CASCADE)."""
    from app.db.connection import get_connection
    from app.db.projects import create_project

    project_id = create_project(name="DS cascade probe")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO discovery_suggestion "
            "(id, project_id, candidate_owner, candidate_repo, candidate_url) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dsug-cascade0", project_id, "acme", "gadget", "https://github.com/acme/gadget"),
        )
        conn.commit()
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM discovery_suggestion WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
    assert remaining == 0, "suggestions should be cascade-deleted with their project"
