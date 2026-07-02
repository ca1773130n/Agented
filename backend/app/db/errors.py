"""Backend-agnostic DB exception aliases (REQ-38).

A bare ``except sqlite3`` IntegrityError catch silently stops firing on
Postgres — the psycopg driver raises ``psycopg.errors.UniqueViolation`` (a
subclass of ``psycopg.errors.IntegrityError``) instead, so an un-swept catch
site would leak an uncaught 500 on PG (research pitfall #2).

These names are exception-class *tuples* that subsume BOTH the sqlite3 and the
psycopg error classes, so ``except errors.IntegrityError`` fires on either
backend. A bare tuple is valid in an ``except`` clause, so call sites keep the
exact same ``except errors.IntegrityError`` / ``except errors.IntegrityError as
e`` shape they had for the sqlite3 class.

psycopg is an optional import: when it is not installed (a pure-SQLite
install), only the sqlite3 classes are aliased — behavior is unchanged.
"""

import sqlite3

try:  # psycopg is a runtime dep, but tolerate a SQLite-only install
    import psycopg

    _PG_INTEGRITY: tuple = (psycopg.errors.IntegrityError,)
    _PG_OPERATIONAL: tuple = (psycopg.errors.OperationalError,)
except Exception:  # pragma: no cover - only when psycopg absent
    _PG_INTEGRITY = ()
    _PG_OPERATIONAL = ()

# Tuples usable directly in ``except``: catch on both SQLite and Postgres.
IntegrityError: tuple = (sqlite3.IntegrityError, *_PG_INTEGRITY)
OperationalError: tuple = (sqlite3.OperationalError, *_PG_OPERATIONAL)

__all__ = ["IntegrityError", "OperationalError"]
