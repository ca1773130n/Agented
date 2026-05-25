"""Repository helpers for ``session_takeaways``."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection
from .ids import generate_id


VALID_KINDS = frozenset({
    "user_preference",
    "discovered_procedure",
    "tool_pattern",
    "constraint",
    "domain_fact",
    "failure_root_cause",
    "success_pattern",
})

VALID_TARGETS = frozenset({
    "memory", "rule", "skill", "knowledge_graph", "claude_md",
})


def insert_many(takeaways: list[dict[str, Any]]) -> list[str]:
    """Bulk insert. Returns the generated ids in order."""
    if not takeaways:
        return []
    rows: list[tuple] = []
    ids: list[str] = []
    for tk in takeaways:
        if tk["kind"] not in VALID_KINDS:
            raise ValueError(f"unknown takeaway kind: {tk['kind']!r}")
        target = tk.get("suggested_target")
        if target is not None and target not in VALID_TARGETS:
            raise ValueError(f"unknown suggested_target: {target!r}")
        tk_id = generate_id("tk")
        ids.append(tk_id)
        rows.append((
            tk_id,
            tk["session_kind"],
            tk["session_id"],
            tk.get("project_id"),
            tk["kind"],
            tk["content"],
            float(tk.get("confidence", 0.5)),
            json.dumps(tk.get("evidence", {}), default=str),
            target,
            json.dumps(tk.get("suggested_payload", {}), default=str),
            tk["extractor_version"],
        ))
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO session_takeaways
                   (id, session_kind, session_id, project_id, kind, content,
                    confidence, evidence_json, suggested_target,
                    suggested_payload_json, extractor_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    return ids


def get(takeaway_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM session_takeaways WHERE id = ?", (takeaway_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_for_project(
    project_id: str,
    *,
    kind: Optional[str] = None,
    applied: Optional[bool] = None,
    dismissed: Optional[bool] = None,
    limit: int = 50,
) -> list[dict]:
    sql = ["SELECT * FROM session_takeaways WHERE project_id = ?"]
    params: list[Any] = [project_id]
    if kind:
        sql.append("AND kind = ?")
        params.append(kind)
    if applied is not None:
        sql.append("AND applied = ?")
        params.append(1 if applied else 0)
    if dismissed is not None:
        sql.append("AND dismissed = ?")
        params.append(1 if dismissed else 0)
    sql.append("ORDER BY created_at DESC LIMIT ?")
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_recent(
    *,
    project_id: Optional[str] = None,
    dismissed: Optional[bool] = None,
    applied: Optional[bool] = None,
    limit: int = 25,
) -> list[dict]:
    sql = ["SELECT * FROM session_takeaways WHERE 1=1"]
    params: list[Any] = []
    if project_id is not None:
        sql.append("AND project_id = ?")
        params.append(project_id)
    if applied is not None:
        sql.append("AND applied = ?")
        params.append(1 if applied else 0)
    if dismissed is not None:
        sql.append("AND dismissed = ?")
        params.append(1 if dismissed else 0)
    sql.append("ORDER BY created_at DESC LIMIT ?")
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_applied(
    takeaway_id: str, *, target: str, asset_id: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE session_takeaways SET
                   applied          = 1,
                   applied_at       = datetime('now'),
                   applied_target   = ?,
                   applied_asset_id = ?
               WHERE id = ?""",
            (target, asset_id, takeaway_id),
        )
        conn.commit()


def mark_dismissed(takeaway_id: str, *, reason: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE session_takeaways SET
                   dismissed        = 1,
                   dismissed_reason = ?
               WHERE id = ?""",
            ((reason or "")[:1000] if reason else None, takeaway_id),
        )
        conn.commit()


def _row_to_dict(row) -> dict:
    d = dict(row)
    for json_key, out_key in (
        ("evidence_json", "evidence"),
        ("suggested_payload_json", "suggested_payload"),
    ):
        try:
            d[out_key] = json.loads(d.pop(json_key) or "{}")
        except (TypeError, ValueError):
            d[out_key] = {}
    d["applied"] = bool(d["applied"])
    d["dismissed"] = bool(d["dismissed"])
    return d
