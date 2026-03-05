"""Database connection management for Agented."""

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


@contextmanager
def get_connection():
    """Return a context manager yielding a sqlite3 Row-factory connection.

    Enables foreign keys and sets busy_timeout for concurrent access.
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
    finally:
        conn.close()
