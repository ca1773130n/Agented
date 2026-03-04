"""Encrypted secrets CRUD operations.

Stores and retrieves secrets with encrypted values. The encrypted_value column
contains Fernet-encrypted ciphertext -- plaintext is NEVER stored in the database.
"""

import datetime
import logging
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_secret_id

logger = logging.getLogger(__name__)


def create_secret(
    name: str,
    encrypted_value: str,
    description: str = "",
    scope: str = "global",
    created_by: str = "system",
) -> str:
    """Create a new secret with an encrypted value. Returns the secret ID."""
    with get_connection() as conn:
        secret_id = _get_unique_secret_id(conn)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute(
            """INSERT INTO secrets (id, name, encrypted_value, description, scope, created_by,
               created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (secret_id, name, encrypted_value, description, scope, created_by, now, now),
        )
        conn.commit()
        return secret_id


def get_secret(secret_id: str) -> Optional[dict]:
    """Get a secret by ID (includes encrypted_value for internal decryption)."""
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        row = conn.execute("SELECT * FROM secrets WHERE id = ?", (secret_id,)).fetchone()
        return row


def get_secret_by_name(name: str) -> Optional[dict]:
    """Get a secret by name (includes encrypted_value for internal decryption)."""
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        row = conn.execute("SELECT * FROM secrets WHERE name = ?", (name,)).fetchone()
        return row


def list_secrets(scope: Optional[str] = None) -> list:
    """List all secrets (metadata only -- NEVER returns encrypted_value)."""
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        if scope:
            rows = conn.execute(
                """SELECT id, name, description, scope, created_by, created_at,
                   updated_at, last_accessed_at FROM secrets WHERE scope = ?
                   ORDER BY created_at DESC""",
                (scope,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name, description, scope, created_by, created_at,
                   updated_at, last_accessed_at FROM secrets
                   ORDER BY created_at DESC"""
            ).fetchall()
        return rows


def update_secret(
    secret_id: str,
    encrypted_value: Optional[str] = None,
    description: Optional[str] = None,
) -> bool:
    """Update a secret's encrypted value and/or description. Returns True if updated."""
    with get_connection() as conn:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        parts = ["updated_at = ?"]
        params = [now]
        if encrypted_value is not None:
            parts.append("encrypted_value = ?")
            params.append(encrypted_value)
        if description is not None:
            parts.append("description = ?")
            params.append(description)
        params.append(secret_id)
        sql = f"UPDATE secrets SET {', '.join(parts)} WHERE id = ?"
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def delete_secret(secret_id: str) -> bool:
    """Delete a secret by ID. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM secrets WHERE id = ?", (secret_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_last_accessed(secret_id: str) -> bool:
    """Update the last_accessed_at timestamp for a secret."""
    with get_connection() as conn:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        cursor = conn.execute(
            "UPDATE secrets SET last_accessed_at = ? WHERE id = ?", (now, secret_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def count_secrets() -> int:
    """Return the total number of secrets in the vault."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()
        return row[0] if row else 0


def _dict_factory(cursor, row):
    """Convert a sqlite3 Row to a dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
