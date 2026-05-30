"""Repository for per-project autonomy policy."""

from __future__ import annotations

from typing import Optional

from app.database import get_connection
from app.models.autonomy_policy import AutonomyPolicy


def get_policy(project_id: str) -> Optional[AutonomyPolicy]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT policy_json FROM project_autonomy_config WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        return AutonomyPolicy.model_validate_json(row["policy_json"])
    except Exception:
        return AutonomyPolicy()


def upsert_policy(project_id: str, policy: AutonomyPolicy) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO project_autonomy_config (project_id, enabled, policy_json, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(project_id) DO UPDATE SET
                   enabled=excluded.enabled, policy_json=excluded.policy_json,
                   updated_at=datetime('now')""",
            (project_id, 1 if policy.enabled else 0, policy.model_dump_json()),
        )
        conn.commit()


def list_enabled() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT project_id, policy_json FROM project_autonomy_config WHERE enabled = 1"
        ).fetchall()
    return [dict(r) for r in rows]
