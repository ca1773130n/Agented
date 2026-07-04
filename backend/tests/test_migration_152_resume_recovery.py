"""Migration 152: redispatch/resume provenance + auto_redispatch flag (Phase 4)."""

from app.db.connection import get_connection


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_migration_152_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 152 in versions
    assert "resume_recovery" in names


def test_fresh_schema_has_all_three_columns(skip_on_pg):
    """create_fresh_schema directly — the fixture DB also runs migrations and
    would mask a missing fresh-DDL edit (Phase-3 lesson)."""
    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    el = {r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")}
    tr = {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    ps = {r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")}
    assert "redispatched_from" in el
    assert "auto_redispatch" in tr
    assert "resumed_from" in ps


def test_migration_152_alter_is_idempotent(skip_on_pg):
    import sqlite3

    from app.db.migrations.v07_features import _migrate_152_resume_recovery

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT UNIQUE)")
    conn.execute("CREATE TABLE triggers (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE project_sessions (id TEXT PRIMARY KEY)")
    _migrate_152_resume_recovery(conn)
    _migrate_152_resume_recovery(conn)  # must not raise
    assert "redispatched_from" in {
        r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")
    }
    assert "auto_redispatch" in {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    assert "resumed_from" in {
        r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")
    }


def test_redispatch_provenance_helpers():
    from app.db.execution_logs import (
        get_redispatch_child,
        set_execution_session_id,
        set_redispatched_from,
    )

    _make_execution("exec-orig")
    _make_execution("exec-new")
    assert get_redispatch_child("exec-orig") is None

    set_redispatched_from("exec-new", "exec-orig")
    child = get_redispatch_child("exec-orig")
    assert child is not None and child["execution_id"] == "exec-new"

    set_execution_session_id("exec-orig", "sess-abc123")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id FROM execution_logs WHERE execution_id = ?", ("exec-orig",)
        ).fetchone()
    assert row["session_id"] == "sess-abc123"
