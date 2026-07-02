# backend/tests/test_verification_records_schema.py
"""Schema + migration for the P5 verification records (Harness-1 Phase 2)."""

from app.db.connection import get_connection


def test_verification_records_table_created_by_fresh_schema():
    with get_connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "verification_records" in tables


def test_create_verification_records_tables_idempotent():
    from app.db.schema._verification_records import create_verification_records_tables

    with get_connection() as conn:
        create_verification_records_tables(conn)
        create_verification_records_tables(conn)
        conn.commit()


def test_migration_150_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 150 in versions
    assert "verification_records" in names


def test_status_check_constraint_rejects_bad_value(skip_on_pg):
    import sqlite3

    from app.db.migrations.v07_features import _migrate_150_verification_records

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT UNIQUE)")
    conn.execute("INSERT INTO execution_logs(execution_id) VALUES ('e1')")
    _migrate_150_verification_records(conn)
    try:
        conn.execute(
            "INSERT INTO verification_records (execution_id, claim, status) VALUES ('e1','c','bogus')"
        )
        raise AssertionError("CHECK constraint should have rejected 'bogus'")
    except sqlite3.IntegrityError:
        pass
