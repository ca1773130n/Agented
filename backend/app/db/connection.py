"""Database connection management for Agented.

SQLite is the zero-config default. When ``config.DATABASE_URL`` is set to a
``postgres://`` / ``postgresql://`` URL (REQ-38), ``get_connection()`` yields a
psycopg-3 connection wrapped in :class:`_PgConnWrapper`, a thin DB-API shim that
lets the SAME raw-SQL call-sites (2,613 ``?`` placeholders) run unchanged on
Postgres: it translates the ``?`` paramstyle to ``%s``, returns rows that
support BOTH ``row["col"]`` and ``row[0]``, and populates ``.lastrowid`` from a
``RETURNING id`` appended to INSERTs. With DATABASE_URL unset the sqlite3 path
below is byte-for-byte unchanged.
"""

import datetime as _dt
import re
import sqlite3
from contextlib import contextmanager

import app.config as config

# Matches safe column-assignment expressions used in dynamic UPDATE statements:
#   "column_name = ?"  or  "updated_at = CURRENT_TIMESTAMP"
_SAFE_UPDATE_EXPR = re.compile(r"^[a-z_][a-z0-9_]* = (?:\?|CURRENT_TIMESTAMP)$")


def safe_set_clause(updates: list) -> str:
    """Return a validated comma-joined SET clause from a list of 'col = ?' expressions.

    All expressions must match ``column_name = ?`` or the literal
    ``updated_at = CURRENT_TIMESTAMP``.  Raises ``ValueError`` for anything else so
    that dynamic column names originating from unexpected sources are rejected before
    they reach the database.

    Example::

        clause = safe_set_clause(["name = ?", "updated_at = CURRENT_TIMESTAMP"])
        conn.execute(f"UPDATE t SET {clause} WHERE id = ?", [name, row_id])
    """
    for expr in updates:
        if not _SAFE_UPDATE_EXPR.match(expr):
            raise ValueError(f"Unsafe expression in SET clause: {expr!r}")
    return ", ".join(updates)


def _is_pg() -> bool:
    """True when a Postgres DATABASE_URL is configured (else SQLite default)."""
    url = config.DATABASE_URL
    return bool(url) and url.startswith(("postgres://", "postgresql://"))


def _translate_params(sql: str) -> str:
    """Translate the sqlite3 ``?`` paramstyle to psycopg's ``%s``.

    The codebase has no literal ``?`` inside string literals (verified by grep),
    so a plain replace is safe. Literal ``%`` must be doubled first so psycopg
    does not read it as a placeholder marker.
    """
    return sql.replace("%", "%%").replace("?", "%s")


# --- Finite SQLite-idiom → Postgres dialect translation (PG path only) -------
# Only the irreducible idiom set from 26-RESEARCH.md §REQ-38 is translated; the
# portable idioms (CURRENT_TIMESTAMP, RETURNING) are already identical on PG and
# are left untouched. This runs ONLY inside _PgConnWrapper, so the SQLite path
# is unaffected.
_AUTOINC_RE = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.IGNORECASE)
_DATETIME_NOW_RE = re.compile(r"datetime\(\s*'now'\s*\)", re.IGNORECASE)
# SQLite's ``BLOB`` column type has no Postgres analogue → ``BYTEA``. Matched as
# an upper-case whole word (the DDL idiom) so it can never touch a lower-case
# identifier or a string literal in DML.
_BLOB_TYPE_RE = re.compile(r"\bBLOB\b")

# `PRAGMA table_info(<table>)` — the only PRAGMA whose result set call-sites read
# (positionally as row[1] / by name as row["name"]). Captures the table name so
# it can be introspected via information_schema on Postgres.
_PRAGMA_TABLE_INFO_RE = re.compile(
    r"^\s*pragma\s+table_info\s*\(\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*\)\s*;?\s*$",
    re.IGNORECASE,
)

# Postgres introspection that returns rows shaped EXACTLY like SQLite's
# `PRAGMA table_info` output: (cid, name, type, notnull, dflt_value, pk). So
# consumers that read row[1]/row["name"] (existing-column guards), row[2]
# (type), or row[3] (notnull flag) keep working, and idempotent ALTERs see the
# real column set instead of an empty one (which would double-add columns).
# `%s` is psycopg's native placeholder — this SQL bypasses `?`→`%s` translation.
_PG_TABLE_INFO_SQL = """
    SELECT (ordinal_position - 1)                          AS cid,
           column_name                                     AS name,
           data_type                                       AS type,
           CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END  AS notnull,
           column_default                                  AS dflt_value,
           0                                               AS pk
    FROM information_schema.columns
    WHERE table_name = %s AND table_schema = current_schema()
    ORDER BY ordinal_position
"""

# `SELECT ... FROM sqlite_master WHERE type='table' AND name=<X>` — the table
# existence-check shape used verbatim at 55+ migration/db call-sites (and the
# init_db bootstrap). sqlite_master has no Postgres analogue; captures the name
# token (already `?`→`%s`-translated, or a 'literal') to re-target
# information_schema. Any OTHER sqlite_master shape fails loud rather than
# silently returning wrong rows.
_SQLITE_MASTER_EXISTS_RE = re.compile(
    r"^\s*select\s+.+?\s+from\s+sqlite_master\s+where\s+type\s*=\s*'table'"
    r"\s+and\s+name\s*=\s*(%s|'[^']*')\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _translate_dialect(sql: str) -> str:
    """Rewrite the finite set of SQLite-only DDL/DML idioms to Postgres.

    - ``INTEGER PRIMARY KEY AUTOINCREMENT`` → ``BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY``
    - ``datetime('now')`` → ``now()``
    - ``BLOB`` → ``BYTEA`` (SQLite binary column type → Postgres binary type)
    (``INSERT OR IGNORE/REPLACE`` is handled in ``_PgConnWrapper.execute`` where
    the ON CONFLICT clause must be positioned before any RETURNING.)
    """
    s = _AUTOINC_RE.sub("BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY", sql)
    s = _DATETIME_NOW_RE.sub("now()", s)
    s = _BLOB_TYPE_RE.sub("BYTEA", s)
    return s


def _sqlite_value(v):
    """Coerce a psycopg-returned value to the shape SQLite would return.

    Timestamp/date columns are declared ``TIMESTAMP``/``DATE`` but SQLite has no
    native date type — every call-site writes ``.isoformat()`` and reads
    ``datetime.fromisoformat(...)``, so on SQLite those columns come back as
    ISO-8601 ``str``. Postgres' native ``TIMESTAMP``/``DATE`` make psycopg return
    ``datetime``/``date``/``time`` objects instead, which breaks the string-based
    call-sites (e.g. ``sessions.get_session_by_token`` →
    ``fromisoformat(datetime)`` → TypeError; ``session_shares.resolve_share_token``
    then fails closed). Coercing back to an ISO string restores byte-for-byte
    parity. Runs ONLY on the Postgres path (inside :class:`_Row`), so the SQLite
    default is untouched.
    """
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    return v


def _hybrid_row_factory(cursor):
    """psycopg row factory yielding rows that mimic ``sqlite3.Row``.

    Supports both ``row["col"]`` and ``row[0]`` plus ``dict(row)`` — so the raw
    call-sites that use either access style keep working on Postgres.
    """
    desc = cursor.description
    cols = [d.name for d in desc] if desc else []

    def make(values):
        return _Row(cols, values)

    return make


class _Row:
    """A sqlite3.Row-compatible row supporting keyed and positional access."""

    __slots__ = ("_cols", "_values", "_map")

    def __init__(self, cols, values):
        self._cols = cols
        # Coerce native PG date/time objects back to the ISO strings SQLite
        # returns, so string-based call-sites keep working (see _sqlite_value).
        self._values = tuple(_sqlite_value(v) for v in values)
        self._map = dict(zip(cols, self._values))

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._map[key]

    def keys(self):
        return list(self._cols)

    def values(self):
        # Not part of sqlite3.Row, but harmless on the PG-only `_Row`: some
        # call-sites treat a fetched row as a plain mapping (`.values()`).
        return list(self._values)

    def items(self):
        # dict-style pairs. Keyed off the name→value map (NOT __iter__, which
        # deliberately yields VALUES to mimic sqlite3.Row). Lets call-sites like
        # users.authenticate() do `{k: v for k, v in row.items()}` on Postgres.
        return list(self._map.items())

    def __iter__(self):
        # sqlite3.Row iterates VALUES, not keys.
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, key):
        return key in self._map

    def get(self, key, default=None):
        return self._map.get(key, default)


class _PgCursor:
    """Cursor-like wrapper exposing the sqlite3 attributes call-sites rely on.

    Two behaviours mirror sqlite3 so raw call-sites work unchanged on Postgres:

    * ``.description`` — a sqlite3-shaped 7-tuple sequence
      ``(name, None, None, None, None, None, None)`` per column. Call-sites read
      ``col[0]`` for the column name (``app/db/grd_ouroboros.py`` and the
      ``_row_to_dict``/``_dict_factory`` helpers in users/rbac/sessions).
    * ``row_factory`` — when the connection had a sqlite-style
      ``row_factory=fn`` set at ``execute()`` time (``fn(cursor, row) -> mapped``),
      fetched rows are passed through it, exactly as sqlite3 applies the
      connection's row_factory to the cursor it creates. With no factory, rows
      are the hybrid :class:`_Row` (positional + keyed).
    """

    __slots__ = ("_cur", "lastrowid", "_row_factory")

    def __init__(self, cur, lastrowid=None, row_factory=None):
        self._cur = cur
        self.lastrowid = lastrowid
        self._row_factory = row_factory

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        """sqlite3-style description: a list of 7-tuples, name in slot 0.

        psycopg exposes ``Column`` objects (name via ``.name``); sqlite3 exposes
        7-item sequences with only the name populated. Call-sites index ``[0]``
        for the name and only care about ordering/length, so we normalise to the
        sqlite3 shape. Returns ``None`` for statements with no result columns
        (e.g. UPDATE/DELETE), matching both drivers.
        """
        desc = self._cur.description
        if desc is None:
            return None
        return [(col.name, None, None, None, None, None, None) for col in desc]

    def _map(self, row):
        if row is None or self._row_factory is None:
            return row
        return self._row_factory(self, row)

    def fetchone(self):
        return self._map(self._cur.fetchone())

    def fetchall(self):
        if self._row_factory is None:
            return self._cur.fetchall()
        return [self._row_factory(self, r) for r in self._cur.fetchall()]

    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()
        if self._row_factory is None:
            return rows
        return [self._row_factory(self, r) for r in rows]

    def __iter__(self):
        if self._row_factory is None:
            return iter(self._cur)
        return (self._row_factory(self, r) for r in self._cur)


class _PgConnWrapper:
    """Thin DB-API shim over a psycopg-3 connection (paramstyle + Row + lastrowid).

    Exposes ``.execute/.commit/.rollback/.close/.cursor`` plus a ``row_factory``
    slot that is HONORED (sqlite3-style): setting ``conn.row_factory = fn``
    before an ``execute()`` makes that cursor's fetches return ``fn(cursor, row)``
    — matching how sqlite3 applies the connection factory to the cursor it
    creates. Auth/RBAC/session code relies on this (``conn.row_factory =
    _row_to_dict`` → real ``dict`` rows). With ``row_factory`` left ``None`` the
    fetches yield the hybrid :class:`_Row` (positional + keyed + mapping).
    """

    def __init__(self, conn):
        self._conn = conn
        # sqlite3-style row factory: honored at execute() time (see _PgCursor).
        self.row_factory = None

    def execute(self, sql, params=()):
        import psycopg

        stripped = sql.lstrip().lower()

        # PRAGMA is SQLite-only. `table_info` must return REAL introspection rows
        # (SQLite shape: cid,name,type,notnull,dflt_value,pk) — call-sites read
        # row[1]/row["name"] to guard idempotent ALTERs, so an empty/NULL row
        # would both crash (IndexError/KeyError) and, if it didn't, double-add
        # existing columns. Every other PRAGMA (foreign_keys, busy_timeout,
        # journal_mode, synchronous, …) is meaningless on PG → harmless no-op.
        if stripped.startswith("pragma"):
            cur = self._conn.cursor(row_factory=_hybrid_row_factory)
            m = _PRAGMA_TABLE_INFO_RE.match(sql)
            if m:
                cur.execute(_PG_TABLE_INFO_SQL, (m.group(1),))
            else:
                cur.execute("SELECT NULL")
            return _PgCursor(cur, row_factory=self.row_factory)

        # sqlite_master is SQLite's catalog and does not exist on Postgres.
        # Translate the dominant existence-check shape to information_schema so
        # init_db bootstrap + the 55 idempotent-migration guards work on PG.
        if "sqlite_master" in stripped:
            m = _SQLITE_MASTER_EXISTS_RE.match(_translate_params(sql))
            if m is None:
                raise NotImplementedError(
                    "Unhandled sqlite_master query on Postgres — rewrite via "
                    f"information_schema. Offending SQL: {sql.strip()[:160]}"
                )
            pg = (
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = current_schema() "
                "AND table_type = 'BASE TABLE' AND table_name = " + m.group(1)
            )
            cur = self._conn.cursor(row_factory=_hybrid_row_factory)
            cur.execute(pg, params)
            return _PgCursor(cur, row_factory=self.row_factory)

        query = _translate_dialect(_translate_params(sql))

        # INSERT OR IGNORE/REPLACE → ON CONFLICT (positioned before RETURNING).
        on_conflict = ""
        low = query.lower()
        if low.startswith("insert or ignore"):
            query = re.sub(
                r"^\s*insert\s+or\s+ignore", "INSERT", query, count=1, flags=re.IGNORECASE
            )
            on_conflict = " ON CONFLICT DO NOTHING"
        elif low.startswith("insert or replace"):
            # `INSERT OR REPLACE` has no universal Postgres translation — the
            # conflict target is unknowable from the statement text, and a plain
            # INSERT silently degrades overwrite→UniqueViolation. So FAIL LOUDLY:
            # every call-site must be swept to an explicit, portable
            # `INSERT … ON CONFLICT (<cols>) DO UPDATE …` (works on both SQLite
            # ≥3.24 and Postgres). See app/db/grd.py and
            # app/services/embedding_service.py for the swept forms.
            raise NotImplementedError(
                "INSERT OR REPLACE cannot be translated to Postgres (no known "
                "conflict target). Rewrite the call-site as an explicit "
                "INSERT ... ON CONFLICT (<cols>) DO UPDATE. Offending SQL: "
                f"{sql.strip()[:160]}"
            )

        is_insert = query.lstrip().lower().startswith("insert")
        want_id = is_insert and "returning" not in query.lower()

        if want_id:
            # Populate .lastrowid via RETURNING id inside a savepoint so a table
            # without an ``id`` column (or an ON CONFLICT no-op) doesn't poison
            # the outer transaction — fall back to a plain execute in that case.
            try:
                with self._conn.transaction():
                    cur = self._conn.cursor(row_factory=_hybrid_row_factory)
                    cur.execute(query + on_conflict + " RETURNING id", params)
                    row = cur.fetchone()
                    lastrowid = row[0] if row is not None else None
                    return _PgCursor(cur, lastrowid, row_factory=self.row_factory)
            except psycopg.Error:
                pass  # retry without RETURNING below

        cur = self._conn.cursor(row_factory=_hybrid_row_factory)
        cur.execute(query + on_conflict, params)
        return _PgCursor(cur, row_factory=self.row_factory)

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor(row_factory=_hybrid_row_factory)
        cur.executemany(_translate_dialect(_translate_params(sql)), seq_of_params)
        return _PgCursor(cur, row_factory=self.row_factory)

    def cursor(self):
        return self._conn.cursor(row_factory=_hybrid_row_factory)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def get_connection():
    """Return a context manager yielding a DB connection.

    Postgres (DATABASE_URL set) → a psycopg-3 connection wrapped by
    :class:`_PgConnWrapper`. Otherwise the unchanged sqlite3 Row-factory path
    (foreign keys ON, busy_timeout, WAL best-effort).
    """
    if _is_pg():
        import psycopg

        conn = psycopg.connect(config.DATABASE_URL, autocommit=False)
        wrapper = _PgConnWrapper(conn)
        try:
            yield wrapper
        except Exception:
            try:
                wrapper.rollback()
            except Exception:
                pass
            raise
        finally:
            wrapper.close()
        return

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # WAL lets readers and a writer proceed concurrently instead of serializing
    # on a single global lock — reduces "database is locked" under the
    # multi-threaded SSE/scheduler workload (03-core M4). Best-effort: some
    # backing stores (e.g. certain network FS) reject WAL; fall back silently.
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.OperationalError:
        pass
    try:
        yield conn
    except Exception:
        # Roll back any half-applied transaction on error so a failed
        # multi-statement write can't leave a partial commit pending for the
        # next caller on this connection (03-core M2). Auto-commit is
        # intentionally NOT added — callers commit explicitly, and committing
        # here would change semantics for read-only/uncommitted-on-purpose paths.
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
