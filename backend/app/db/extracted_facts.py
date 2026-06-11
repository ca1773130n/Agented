"""Repository helpers for ``extracted_facts``.

Facts are extracted from leader-chat answers and persisted with provenance
(evidence sources, confidence, session/project scope). Dedup is
session-scoped: ``dedup_hash = sha256(f"{project_id or ''}|{session_id}|{claim}")``.
A later session re-asserting the same claim still creates a NEW row so
``list_for_session`` stays accurate per-session (cross-session dedup is NOT
attempted by design).
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from .connection import get_connection


def _make_dedup_hash(project_id: Optional[str], session_id: str, claim: str) -> str:
    raw = f"{project_id or ''}|{session_id}|{claim}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["evidence"] = json.loads(d.pop("evidence_json") or "[]")
    except (TypeError, ValueError):
        d["evidence"] = []
    return d


def insert_facts(
    session_id: str,
    *,
    super_agent_id: Optional[str],
    project_id: Optional[str],
    facts: list[dict],
) -> int:
    """Insert a list of facts, skipping any that already exist for this session.

    Each fact dict must have ``claim``; ``evidence`` (list) and ``confidence``
    (float) are optional and default to ``[]`` / ``0.5``.

    Returns the number of rows actually inserted (0 when all duplicated).
    """
    if not facts:
        return 0

    rows = []
    for fact in facts:
        claim = fact["claim"]
        dedup_hash = _make_dedup_hash(project_id, session_id, claim)
        rows.append(
            (
                session_id,
                super_agent_id,
                project_id,
                claim,
                json.dumps(fact.get("evidence", []), default=str),
                float(fact.get("confidence", 0.5)),
                dedup_hash,
            )
        )

    inserted = 0
    with get_connection() as conn:
        for row in rows:
            cur = conn.execute(
                """INSERT OR IGNORE INTO extracted_facts
                       (session_id, super_agent_id, project_id, claim,
                        evidence_json, confidence, dedup_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
            inserted += cur.rowcount
        conn.commit()
    return inserted


def list_for_session(session_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM extracted_facts WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_for_project(project_id: str, *, limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM extracted_facts WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, int(limit)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_for_project(project_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM extracted_facts WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return row[0] if row else 0
