"""Repository for the typed tool_use evidence ledger (Harness-1 Phase 2, P3).

See ``app.db.schema._harness_evidence`` for the DDL. ``record_tool_use`` is
the core primitive: it assigns the next per-session ``seq`` and inserts one
row in a single transaction, returning the assigned ``seq``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection


def record_tool_use(
    session_id: str,
    *,
    super_agent_id: Optional[str],
    tool_name: str,
    tool_input: Any,
    tool_use_id: Optional[str] = None,
) -> int:
    """Append one tool_use row with the next per-session ``seq``. Returns seq.

    The ordinal is computed inside the INSERT (a correlated subquery), so it is
    evaluated while SQLite holds the write lock — assignment is atomic and
    cannot race across connections. ``UNIQUE(session_id, seq)`` is the backstop.
    """
    payload = json.dumps(tool_input, default=str)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO harness_evidence "
            "(session_id, super_agent_id, seq, tool_name, tool_input_json, tool_use_id) "
            "VALUES (?, ?, "
            "  (SELECT COALESCE(MAX(seq), 0) + 1 FROM harness_evidence WHERE session_id = ?), "
            "  ?, ?, ?)",
            (session_id, super_agent_id, session_id, tool_name, payload, tool_use_id),
        )
        seq = conn.execute(
            "SELECT seq FROM harness_evidence WHERE id = ?", (cur.lastrowid,)
        ).fetchone()[0]
        conn.commit()
    return int(seq)


def list_evidence(session_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_evidence WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_evidence(session_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM harness_evidence WHERE session_id = ?", (session_id,)
        ).fetchone()
    return int(row[0])


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["tool_input"] = json.loads(d.pop("tool_input_json") or "{}")
    except (TypeError, ValueError):
        d["tool_input"] = {}
    return d
