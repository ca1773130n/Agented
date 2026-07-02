"""Adapter tests for the Postgres DB-API shim (REQ-38, plan 26-01).

The unit-level checks (paramstyle translation, hybrid Row, unified error
aliasing, _is_pg default) run on any machine — no Postgres required. The
init_db-on-PG smoke test and the representative round-trip are SKIPPED cleanly
when no Postgres ``DATABASE_URL`` is configured, so the zero-config local run
stays SQLite-only and green.
"""

import os
import sqlite3

import pytest

import app.config as config
from app.db import errors
from app.db.connection import (
    _is_pg,
    _PgConnWrapper,
    _Row,
    _SQLITE_MASTER_EXISTS_RE,
    _translate_dialect,
    _translate_params,
)

_PG_URL = os.environ.get("DATABASE_URL", "")
_HAS_PG = _PG_URL.startswith(("postgres://", "postgresql://"))
_pg_only = pytest.mark.skipif(not _HAS_PG, reason="no Postgres DATABASE_URL configured")


# --------------------------------------------------------------------------- #
# Unit: paramstyle + dialect translation (no DB needed)
# --------------------------------------------------------------------------- #


def test_paramstyle_translation():
    assert _translate_params("SELECT ? , ?") == "SELECT %s , %s"
    assert _translate_params("INSERT INTO t (a, b) VALUES (?, ?)") == (
        "INSERT INTO t (a, b) VALUES (%s, %s)"
    )
    # literal % must be doubled so psycopg does not read it as a placeholder
    assert _translate_params("name LIKE ?") == "name LIKE %s"
    assert "%%" in _translate_params("x LIKE '%foo%'")


def test_dialect_autoincrement_to_identity():
    ddl = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, n TEXT)"
    out = _translate_dialect(ddl)
    assert "IDENTITY" in out
    assert "AUTOINCREMENT" not in out


def test_dialect_datetime_now():
    assert _translate_dialect("SELECT datetime('now')") == "SELECT now()"


def test_sqlite_master_exists_translation_regex():
    # canonical existence-check shape (literal name) — the 55-site pattern
    m = _SQLITE_MASTER_EXISTS_RE.match(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    assert m and m.group(1) == "'schema_version'"
    # parameterized form (after ?->%s translation)
    m = _SQLITE_MASTER_EXISTS_RE.match(
        _translate_params("SELECT name FROM sqlite_master WHERE type='table' AND name=?")
    )
    assert m and m.group(1) == "%s"
    # an unhandled sqlite_master shape must NOT match (wrapper fails loud instead)
    assert _SQLITE_MASTER_EXISTS_RE.match("SELECT sql FROM sqlite_master WHERE name='t'") is None


# --------------------------------------------------------------------------- #
# Unit: hybrid Row supports keyed AND positional access
# --------------------------------------------------------------------------- #


def test_hybrid_row_dual_access():
    row = _Row(["id", "name"], ["team-1", "Alpha"])
    assert row["id"] == "team-1"
    assert row[0] == "team-1"
    assert row["name"] == "Alpha"
    assert row[1] == "Alpha"
    assert dict(row) == {"id": "team-1", "name": "Alpha"}
    assert row.keys() == ["id", "name"]
    assert "name" in row
    assert len(row) == 2


# --------------------------------------------------------------------------- #
# Unit: unified error type catches BOTH backends' integrity errors
# --------------------------------------------------------------------------- #


def test_integrity_error_unified():
    # sqlite3.IntegrityError is caught by errors.IntegrityError
    caught_sqlite = False
    try:
        raise sqlite3.IntegrityError("dup")
    except errors.IntegrityError:
        caught_sqlite = True
    assert caught_sqlite

    # psycopg UniqueViolation (a psycopg IntegrityError) is caught too
    import psycopg

    caught_pg = False
    try:
        raise psycopg.errors.UniqueViolation
    except errors.IntegrityError:
        caught_pg = True
    assert caught_pg


def test_operational_error_unified():
    caught = False
    try:
        raise sqlite3.OperationalError("boom")
    except errors.OperationalError:
        caught = True
    assert caught


# --------------------------------------------------------------------------- #
# Unit: _is_pg default is SQLite (zero-config invariant)
# --------------------------------------------------------------------------- #


def test_is_pg_default_false(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    assert _is_pg() is False


def test_is_pg_true_for_postgres_url(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@localhost/db")
    assert _is_pg() is True
    monkeypatch.setattr(config, "DATABASE_URL", "postgres://u:p@localhost/db")
    assert _is_pg() is True


def test_pg_conn_wrapper_exists():
    # S2: the shim class is importable and exposes the DB-API surface.
    for attr in ("execute", "commit", "rollback", "close", "cursor"):
        assert hasattr(_PgConnWrapper, attr)


# --------------------------------------------------------------------------- #
# Unit: PRAGMA table_info → real Postgres introspection (26-01 crit)
# --------------------------------------------------------------------------- #


class _FakeCur:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))

    def fetchone(self):
        return None


class _FakeConn:
    """Minimal psycopg-conn stand-in: records the SQL the wrapper issues."""

    def __init__(self):
        self.cur = _FakeCur()

    def cursor(self, row_factory=None):
        return self.cur


def test_pragma_table_info_regex_extracts_table_name():
    from app.db.connection import _PRAGMA_TABLE_INFO_RE

    for sql, name in [
        ("PRAGMA table_info(bots)", "bots"),
        ("  pragma table_info( team_members )", "team_members"),
        ('PRAGMA table_info("projects")', "projects"),
        ("PRAGMA table_info(execution_logs);", "execution_logs"),
    ]:
        m = _PRAGMA_TABLE_INFO_RE.match(sql)
        assert m is not None and m.group(1) == name
    # a non-table_info PRAGMA must NOT match (stays a no-op)
    assert _PRAGMA_TABLE_INFO_RE.match("PRAGMA foreign_keys = ON") is None


def test_pg_table_info_sql_has_sqlite_shape():
    from app.db.connection import _PG_TABLE_INFO_SQL

    # rows must be shaped like SQLite's (cid,name,type,notnull,dflt_value,pk)
    for col in ("cid", "name", "type", "notnull", "dflt_value", "pk"):
        assert col in _PG_TABLE_INFO_SQL
    assert "information_schema.columns" in _PG_TABLE_INFO_SQL


def test_pragma_table_info_routes_to_introspection():
    conn = _FakeConn()
    wrapper = _PgConnWrapper(conn)
    wrapper.execute("PRAGMA table_info(team_members)")
    sql, params = conn.cur.calls[-1]
    assert "information_schema.columns" in sql
    assert params == ("team_members",)


def test_pragma_other_is_noop_select_null():
    conn = _FakeConn()
    wrapper = _PgConnWrapper(conn)
    wrapper.execute("PRAGMA foreign_keys = ON")
    sql, _params = conn.cur.calls[-1]
    assert sql == "SELECT NULL"


# --------------------------------------------------------------------------- #
# Unit: INSERT OR REPLACE fails loudly (no silent overwrite→UniqueViolation)
# --------------------------------------------------------------------------- #


def test_insert_or_replace_raises_not_implemented():
    conn = _FakeConn()
    wrapper = _PgConnWrapper(conn)
    with pytest.raises(NotImplementedError):
        wrapper.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))
    # it must fail BEFORE issuing any SQL to the cursor
    assert conn.cur.calls == []


# --------------------------------------------------------------------------- #
# Postgres-only smoke + round-trip (skipped without DATABASE_URL)
# --------------------------------------------------------------------------- #


@_pg_only
def test_init_db_postgres_smoke(monkeypatch):
    import psycopg

    monkeypatch.setattr(config, "DATABASE_URL", _PG_URL)
    with psycopg.connect(_PG_URL, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")

    from app.db.migrations._runner import init_db

    init_db()  # must run clean on Postgres

    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
            ("triggers",),
        ).fetchone()
        assert row is not None


@_pg_only
def test_pg_round_trip(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", _PG_URL)
    from app.db.teams import create_team, get_team

    # create_team returns the new team_id (str); round-trip it back through
    # get_team (dict) to prove an INSERT + SELECT works end-to-end on Postgres.
    team_id = create_team(name="PG Team", description="round trip")
    assert team_id is not None
    fetched = get_team(team_id)
    assert fetched is not None
    assert fetched["name"] == "PG Team"
