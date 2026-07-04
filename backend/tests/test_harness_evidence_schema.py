"""Schema + migration for the P3 evidence ledger (Harness-1 Phase 2)."""

from app.db.connection import get_connection


def test_harness_evidence_table_created_by_fresh_schema():
    with get_connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "harness_evidence" in tables


def test_create_harness_evidence_tables_idempotent():
    from app.db.schema._harness_evidence import create_harness_evidence_tables

    with get_connection() as conn:
        create_harness_evidence_tables(conn)
        create_harness_evidence_tables(conn)  # must not raise
        conn.commit()


def test_migration_149_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 149 in versions
    assert "harness_evidence" in names


def test_migration_149_creates_table_on_existing_db(skip_on_pg):
    import sqlite3

    from app.db.migrations.v07_features import _migrate_149_harness_evidence

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE super_agent_sessions (id TEXT PRIMARY KEY, super_agent_id TEXT)")
    _migrate_149_harness_evidence(conn)
    _migrate_149_harness_evidence(conn)  # idempotent
    tabs = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "harness_evidence" in tabs
