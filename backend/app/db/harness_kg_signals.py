"""Repository for Phase E2 Tesserae-KG-derived evolution signals.

A *signal* is a piece of KG-discovered guidance (prose answer to a
question) with a dedup ``signal_id``, a decayed ``weight``, and an
``already_forged`` flag. Signals (in later tasks) seed evolution rounds.
"""

from __future__ import annotations

from typing import Optional

from app.database import get_connection
from app.db.schema._harness_kg_signals import create_harness_kg_signals_tables


def _ensure_kg_signal_tables(conn) -> None:
    """Idempotent CREATE TABLE/INDEX — safe on a DB that predates the table."""
    create_harness_kg_signals_tables(conn)


def record_signal(
    *,
    signal_id: str,
    project_id: str,
    question: str,
    content: str,
    weight: float,
    already_forged: bool,
    now: str,
    round_id: Optional[str] = None,
) -> dict:
    """UPSERT a signal. ``first_seen_at`` is preserved on conflict (set only
    on first insert); ``captured_at``/``weight``/``already_forged``/``content``/
    ``round_id`` refresh. Returns the stored row as a dict."""
    with get_connection() as conn:
        _ensure_kg_signal_tables(conn)
        conn.execute(
            """INSERT INTO harness_kg_signals (
                   signal_id, project_id, round_id, question, content,
                   weight, already_forged, first_seen_at, captured_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(signal_id) DO UPDATE SET
                   captured_at=excluded.captured_at,
                   weight=excluded.weight,
                   already_forged=excluded.already_forged,
                   content=excluded.content,
                   round_id=excluded.round_id""",
            (
                signal_id,
                project_id,
                round_id,
                question,
                content,
                float(weight),
                1 if already_forged else 0,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM harness_kg_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
    return dict(row)


def get_signal(signal_id: str) -> Optional[dict]:
    with get_connection() as conn:
        _ensure_kg_signal_tables(conn)
        row = conn.execute(
            "SELECT * FROM harness_kg_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
    return dict(row) if row else None


def list_signals(project_id: str, *, limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        _ensure_kg_signal_tables(conn)
        rows = conn.execute(
            "SELECT * FROM harness_kg_signals WHERE project_id = ? "
            "ORDER BY captured_at DESC LIMIT ?",
            (project_id, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def first_seen_at_for(signal_id: str) -> Optional[str]:
    with get_connection() as conn:
        _ensure_kg_signal_tables(conn)
        row = conn.execute(
            "SELECT first_seen_at FROM harness_kg_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
    return row["first_seen_at"] if row else None
