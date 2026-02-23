"""Database connection management for Agented."""

import sqlite3
from contextlib import contextmanager

import app.config as config


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
