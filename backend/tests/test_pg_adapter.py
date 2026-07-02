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


# --------------------------------------------------------------------------- #
# Unit: _Row full-mapping methods + _PgCursor.description + honored row_factory
# (codex #4 — auth/RBAC/session use row.items()/.values(), cursor.description,
#  and set a sqlite-style conn.row_factory=_row_to_dict).
# --------------------------------------------------------------------------- #


def test_hybrid_row_coerces_pg_datetime_to_iso_string():
    # PG returns native datetime/date for TIMESTAMP/DATE columns; SQLite returns
    # ISO strings. _Row must coerce so `datetime.fromisoformat(row[col])` works.
    import datetime as dt

    when = dt.datetime(2026, 6, 29, 12, 34, 56, tzinfo=dt.timezone.utc)
    row = _Row(["id", "expires_at"], ["sess-1", when])
    assert row["expires_at"] == when.isoformat()
    assert isinstance(row["expires_at"], str)
    # round-trips back through fromisoformat (the sessions.py call-site)
    assert dt.datetime.fromisoformat(row["expires_at"]) == when
    # plain date and non-temporal values pass through appropriately
    d = _Row(["d", "n"], [dt.date(2026, 1, 2), 7])
    assert d["d"] == "2026-01-02" and d["n"] == 7


def test_hybrid_row_items_and_values():
    row = _Row(["id", "name"], ["team-1", "Alpha"])
    # dict-style mapping methods that auth/RBAC call-sites rely on
    assert row.values() == ["team-1", "Alpha"]
    assert row.items() == [("id", "team-1"), ("name", "Alpha")]
    assert row.get("name") == "Alpha"
    assert row.get("missing", "d") == "d"
    # authenticate()-shaped comprehension works:
    assert {k: v for k, v in row.items() if k != "name"} == {"id": "team-1"}
    # __iter__ still yields VALUES (sqlite3.Row semantics), NOT keys — unchanged
    assert list(row) == ["team-1", "Alpha"]


class _FakeCol:
    """psycopg Column stand-in: only ``.name`` is read by the adapter."""

    def __init__(self, name):
        self.name = name


class _FakeResultCur:
    """Minimal psycopg-cursor stand-in returning pre-seeded rows."""

    def __init__(self, cols, rows):
        self._cols = cols
        self._rows = list(rows)
        self.description = [_FakeCol(c) for c in cols] if cols is not None else None
        self.rowcount = len(self._rows)

    def execute(self, sql, params=()):
        pass

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self):
        return iter(self._rows)


def _row_to_dict(cursor, row):
    # exact shape of the helper in users.py / rbac.py / sessions.py
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def test_pg_cursor_description_is_sqlite_7tuple():
    from app.db.connection import _PgCursor

    cur = _FakeResultCur(["id", "email"], [])
    desc = _PgCursor(cur).description
    assert [c[0] for c in desc] == ["id", "email"]  # name in slot 0
    assert all(len(c) == 7 for c in desc)  # sqlite3 7-tuple shape
    assert all(c[1] is None for c in desc)  # only the name is populated
    # non-result statements (UPDATE/DELETE) → None, matching both drivers
    assert _PgCursor(_FakeResultCur(None, [])).description is None


def test_pg_cursor_honors_row_factory():
    from app.db.connection import _PgCursor

    seeded = _Row(["id", "email"], ["u-1", "a@b.c"])
    cur = _FakeResultCur(["id", "email"], [seeded])
    got = _PgCursor(cur, row_factory=_row_to_dict).fetchone()
    assert got == {"id": "u-1", "email": "a@b.c"}
    assert type(got) is dict  # a real dict, not a _Row


class _FakeSelectConn:
    def __init__(self, cols, rows):
        self._cols, self._rows = cols, rows

    def cursor(self, row_factory=None):
        return _FakeResultCur(self._cols, self._rows)


def test_wrapper_execute_honors_connection_row_factory():
    # sqlite-style: set conn.row_factory=fn BEFORE execute → fetched rows mapped.
    conn = _FakeSelectConn(["id", "email"], [_Row(["id", "email"], ["u-1", "a@b.c"])])
    wrapper = _PgConnWrapper(conn)
    wrapper.row_factory = _row_to_dict
    row = wrapper.execute("SELECT id, email FROM users WHERE id = ?", ("u-1",)).fetchone()
    assert row == {"id": "u-1", "email": "a@b.c"}

    # with no factory the hybrid _Row (positional + keyed) is returned unchanged
    conn2 = _FakeSelectConn(["id", "email"], [_Row(["id", "email"], ["u-1", "a@b.c"])])
    r2 = _PgConnWrapper(conn2).execute("SELECT id, email FROM users", ()).fetchone()
    assert r2["id"] == "u-1" and r2[0] == "u-1"
