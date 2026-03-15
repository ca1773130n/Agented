"""Database functions for onboarding automation steps."""

from .connection import get_connection
from .ids import generate_id

STEP_ID_PREFIX = "step-"
STEP_ID_LENGTH = 6


def _generate_step_id() -> str:
    return generate_id(STEP_ID_PREFIX, STEP_ID_LENGTH)


def get_steps(trigger_id: str) -> list[dict]:
    """Return all onboarding steps for a trigger, ordered by step_order."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, trigger_id, step_order, name, description, type, enabled,
                   delay_minutes, created_at, updated_at
            FROM onboarding_steps
            WHERE trigger_id = ?
            ORDER BY step_order ASC
            """,
            (trigger_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
    for row in rows:
        row["enabled"] = bool(row["enabled"])
    return rows


def upsert_steps(trigger_id: str, steps: list[dict]) -> None:
    """Replace all onboarding steps for a trigger (DELETE + INSERT in one transaction)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM onboarding_steps WHERE trigger_id = ?", (trigger_id,))
        for step in steps:
            step_id = step.get("id") or _generate_step_id()
            conn.execute(
                """
                INSERT INTO onboarding_steps
                    (id, trigger_id, step_order, name, description, type, enabled, delay_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    trigger_id,
                    step.get("step_order", 0),
                    step.get("name", ""),
                    step.get("description", ""),
                    step.get("type", "custom"),
                    1 if step.get("enabled", True) else 0,
                    step.get("delay_minutes", 0),
                ),
            )
        conn.commit()
