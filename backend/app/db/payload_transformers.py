"""CRUD operations for payload_transformers table.

Stores per-trigger (or global) JSONPath/jq transform rules that reshape
incoming webhook payloads before they reach the prompt template engine.
"""

import logging

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)


def _generate_ptx_id() -> str:
    return generate_id("ptx-", 6)


def get_transformer_by_trigger(trigger_id: str) -> dict | None:
    """Return the transformer row for a given trigger_id, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, trigger_id, name, rules, created_at, updated_at "
            "FROM payload_transformers WHERE trigger_id = ?",
            (trigger_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "trigger_id": row[1],
        "name": row[2],
        "rules": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def upsert_transformer(trigger_id: str, name: str, rules_json: str) -> str:
    """Insert or replace the transformer for a trigger_id.

    Returns the id of the upserted row.
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM payload_transformers WHERE trigger_id = ?", (trigger_id,)
        ).fetchone()

        if existing:
            row_id = existing[0]
            conn.execute(
                "UPDATE payload_transformers SET name = ?, rules = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE trigger_id = ?",
                (name, rules_json, trigger_id),
            )
        else:
            row_id = _generate_ptx_id()
            conn.execute(
                "INSERT INTO payload_transformers (id, trigger_id, name, rules) "
                "VALUES (?, ?, ?, ?)",
                (row_id, trigger_id, name, rules_json),
            )
        conn.commit()
    return row_id


def delete_transformer(trigger_id: str) -> bool:
    """Delete the transformer for a trigger_id. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM payload_transformers WHERE trigger_id = ?", (trigger_id,)
        )
        conn.commit()
    return cursor.rowcount > 0
