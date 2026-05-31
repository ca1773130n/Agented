"""Repository for Phase E forge propagation (evidence, shared bindings, adoptions)."""

from __future__ import annotations

import math
from typing import Optional

from app.database import get_connection


def record_evidence(
    *, fingerprint: str, kind: str, asset_id: str, project_id: str, eval_score: float
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO forge_promotion_evidence (fingerprint, kind, asset_id, project_id, eval_score) "
            "VALUES (?, ?, ?, ?, ?)",
            (fingerprint, kind, str(asset_id), project_id, float(eval_score)),
        )
        conn.commit()


def promotion_score(fingerprint: str, *, half_life_days: float = 30.0) -> float:
    """Time-decayed sum of eval scores for a fingerprint:
    sum(eval_score * 2**(-age_days/half_life))."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT eval_score, (julianday('now') - julianday(created_at)) AS age_days "
            "FROM forge_promotion_evidence WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchall()
    total = 0.0
    for r in rows:
        age = max(0.0, float(r["age_days"] or 0.0))
        total += float(r["eval_score"]) * math.exp(-math.log(2) / half_life_days * age)
    return total


def create_shared_binding(
    *, scope: str, kind: str, asset_id: str, fingerprint: str
) -> Optional[int]:
    """Idempotent on UNIQUE(scope, kind, fingerprint) — returns existing id on conflict."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO shared_forge_bindings (scope, kind, asset_id, fingerprint) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(scope, kind, fingerprint) DO NOTHING",
            (scope, kind, str(asset_id), fingerprint),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM shared_forge_bindings WHERE scope=? AND kind=? AND fingerprint=?",
            (scope, kind, fingerprint),
        ).fetchone()
    return int(row["id"]) if row else None


def get_shared_binding(shared_binding_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM shared_forge_bindings WHERE id = ?", (int(shared_binding_id),)
        ).fetchone()
    return dict(row) if row else None


def list_shared_bindings(*, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM shared_forge_bindings"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY created_at DESC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def record_adoption(*, project_id: str, shared_binding_id: int, state: str = "adopted") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_shared_forge_adoptions (project_id, shared_binding_id, state) "
            "VALUES (?, ?, ?) ON CONFLICT(project_id, shared_binding_id) DO UPDATE SET state=excluded.state",
            (project_id, int(shared_binding_id), state),
        )
        conn.commit()


def is_adopted(project_id: str, shared_binding_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM project_shared_forge_adoptions WHERE project_id=? AND shared_binding_id=?",
            (project_id, int(shared_binding_id)),
        ).fetchone()
    return row is not None
