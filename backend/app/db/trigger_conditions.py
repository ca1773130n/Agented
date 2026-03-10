"""Database functions for trigger condition rules."""

import json
from typing import Optional

from .connection import get_connection
from .ids import generate_id


CONDITION_ID_PREFIX = "tcond-"
CONDITION_ID_LENGTH = 6


def _generate_condition_id(conn) -> str:
    while True:
        cid = generate_id(CONDITION_ID_PREFIX, CONDITION_ID_LENGTH)
        cur = conn.execute("SELECT id FROM trigger_conditions WHERE id = ?", (cid,))
        if cur.fetchone() is None:
            return cid


def list_trigger_conditions(trigger_id: str) -> list:
    """Return all condition rules for a trigger, ordered by creation time."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, trigger_id, name, description, enabled, logic, conditions_json,
                   created_at, updated_at
            FROM trigger_conditions
            WHERE trigger_id = ?
            ORDER BY created_at
            """,
            (trigger_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    for row in rows:
        row["conditions"] = json.loads(row.pop("conditions_json") or "[]")
    return rows


def get_trigger_condition(condition_id: str) -> Optional[dict]:
    """Return a single condition rule by ID, or None if not found."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, trigger_id, name, description, enabled, logic, conditions_json,
                   created_at, updated_at
            FROM trigger_conditions
            WHERE id = ?
            """,
            (condition_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    result = dict(row)
    result["conditions"] = json.loads(result.pop("conditions_json") or "[]")
    return result


def create_trigger_condition(
    trigger_id: str,
    name: str,
    description: str = "",
    enabled: bool = True,
    logic: str = "AND",
    conditions: list = None,
) -> Optional[str]:
    """Insert a new trigger condition rule. Returns the new ID or None on error."""
    conditions_json = json.dumps(conditions or [])
    with get_connection() as conn:
        cid = _generate_condition_id(conn)
        conn.execute(
            """
            INSERT INTO trigger_conditions
                (id, trigger_id, name, description, enabled, logic, conditions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, trigger_id, name, description, 1 if enabled else 0, logic, conditions_json),
        )
        conn.commit()
    return cid


def update_trigger_condition(
    condition_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[bool] = None,
    logic: Optional[str] = None,
    conditions: Optional[list] = None,
) -> bool:
    """Update an existing trigger condition rule. Returns True if a row was updated."""
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if enabled else 0)
    if logic is not None:
        updates.append("logic = ?")
        params.append(logic)
    if conditions is not None:
        updates.append("conditions_json = ?")
        params.append(json.dumps(conditions))
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params.append(condition_id)
    sql = f"UPDATE trigger_conditions SET {', '.join(updates)} WHERE id = ?"
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def delete_trigger_condition(condition_id: str) -> bool:
    """Delete a trigger condition rule. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM trigger_conditions WHERE id = ?", (condition_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
