"""Phase 21 (21-01) sanity tests for the one-click team harness setup
persistence floor: migration 159, the harness_setup_status helpers, and the
harness_setup_steps upsert.

Maps EVAL S1 (schema + double-apply no-op) and S2 (status defaults "none").
"""

from app.db.migrations.v07_features import _migrate_159_harness_setup
from app.db.projects import (
    create_project,
    get_harness_setup_status,
    get_harness_setup_steps,
    set_harness_setup_status,
    update_project,
    upsert_harness_setup_step,
)


def _pragma_table_info(conn, table):
    return list(conn.execute(f"PRAGMA table_info({table})"))


def test_migration_adds_column_and_table(isolated_db):
    """S1: column + table present, correct PK, double-apply is a no-op."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        proj_cols = {r[1] for r in _pragma_table_info(conn, "projects")}
        assert "harness_setup_status" in proj_cols

        steps_cols = {r[1] for r in _pragma_table_info(conn, "harness_setup_steps")}
        assert steps_cols >= {
            "project_id",
            "step_key",
            "status",
            "detail",
            "fingerprint",
            "updated_at",
        }

        # PK is (project_id, step_key) — pk column of PRAGMA table_info is index 5.
        pk = {r[1] for r in _pragma_table_info(conn, "harness_setup_steps") if r[5] > 0}
        assert pk == {"project_id", "step_key"}

        # Double-apply raises nothing and changes nothing.
        _migrate_159_harness_setup(conn)
        _migrate_159_harness_setup(conn)
        conn.commit()

        proj_cols_after = {r[1] for r in _pragma_table_info(conn, "projects")}
        assert proj_cols_after == proj_cols


def test_get_harness_setup_status_defaults_none(isolated_db):
    """S2: a fresh project's status coerces NULL -> 'none'."""
    pid = create_project(name="harness-fresh")
    assert pid is not None
    assert get_harness_setup_status(pid) == "none"


def test_set_and_get_roundtrip(isolated_db):
    pid = create_project(name="harness-roundtrip")
    set_harness_setup_status(pid, "running")
    assert get_harness_setup_status(pid) == "running"
    # update_project kwarg also persists.
    update_project(pid, harness_setup_status="ready")
    assert get_harness_setup_status(pid) == "ready"


def test_upsert_step_idempotent(isolated_db):
    pid = create_project(name="harness-steps")
    upsert_harness_setup_step(pid, "grd_init", "running", detail="starting")
    upsert_harness_setup_step(pid, "grd_init", "ok", detail="done", fingerprint="abc")

    steps = get_harness_setup_steps(pid)
    assert len(steps) == 1
    row = steps[0]
    assert row["step_key"] == "grd_init"
    assert row["status"] == "ok"
    assert row["detail"] == "done"
    assert row["fingerprint"] == "abc"
    assert row["updated_at"]
