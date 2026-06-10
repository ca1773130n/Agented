"""Repository for durable verification records (Harness-1 Phase 2, P5)."""

from __future__ import annotations

from typing import Optional

from .connection import get_connection


def record_verification(
    execution_id: str,
    claim: str,
    status: str = "pending",
    evidence_ref: Optional[str] = None,
) -> int:
    """Insert a verification record. Sets ``checked_at`` when terminal
    (status != 'pending'). Returns the new row id."""
    checked_at_expr = "datetime('now')" if status != "pending" else "NULL"
    with get_connection() as conn:
        cur = conn.execute(
            f"INSERT INTO verification_records "
            f"(execution_id, claim, status, evidence_ref, checked_at) "
            f"VALUES (?, ?, ?, ?, {checked_at_expr})",
            (execution_id, claim, status, evidence_ref),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_verifications(execution_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM verification_records WHERE execution_id = ? ORDER BY id ASC",
            (execution_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def has_failed(execution_id: str) -> bool:
    """True iff at least one record for this execution is 'failed'. The
    post-hoc gate predicate."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM verification_records "
            "WHERE execution_id = ? AND status = 'failed' LIMIT 1",
            (execution_id,),
        ).fetchone()
    return row is not None
