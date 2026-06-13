"""Raw-SQLite repo for the repeated_request_signals store (Phase 22, REQ-22).

The UPSERT here is the heart of the self-improvement loop's salience model:
each sighting of the same normalized request *accumulates* evidence instead of
decaying it. ``occurrence_count`` grows by 1 per upsert, ``first_seen_at`` is
written only on the original INSERT (never in the ON CONFLICT branch), and
``example_session_ids`` keeps the 5 most-recent distinct sessions (FIFO drop).

The embedding is stored as a BLOB via ``embedding_service.serialize_embedding``
— the same encoding ``agent_memory`` uses — so the detector (22-03) can run
cosine matching without re-embedding stored requests. When embedding is
disabled (``embed_text`` returned None) the column stays NULL and the request
coalesces on the exact normalized hash (EVAL A1).
"""

from __future__ import annotations

import hashlib
import json
import re

from app.services.embedding_service import deserialize_embedding, serialize_embedding
from app.utils.timezone import utc_now_iso

from ..models.repeated_request_signal import RepeatedRequestSignal
from .connection import get_connection

# Phase-22 design constant: the most-recent N distinct sessions kept as
# provenance examples on each signal row.
_MAX_EXAMPLE_SESSION_IDS = 5

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_request_hash(text: str) -> str:
    """Normalize request text (lowercase, collapse whitespace, strip) then
    return its sha256 hexdigest.

    This is BOTH the UPSERT conflict key and the embed-disabled exact-match
    key: verbatim repeats (modulo case/whitespace) coalesce onto one row;
    paraphrases hash differently and stay separate.
    """
    normalized = _WHITESPACE_RE.sub(" ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _fifo_merge(existing: list[str], session_id: str) -> list[str]:
    """Append ``session_id`` (if not already present) and keep the last N."""
    if session_id in existing:
        return existing[-_MAX_EXAMPLE_SESSION_IDS:]
    return (existing + [session_id])[-_MAX_EXAMPLE_SESSION_IDS:]


def upsert_signal(
    *,
    request_hash: str,
    project_id: str | None,
    session_kind: str,
    representative_text: str,
    embedding: list[float] | None,
    session_id: str,
    now: str | None = None,
) -> None:
    """Insert a new signal or accumulate evidence onto an existing one.

    On conflict (same ``request_hash``): increment ``occurrence_count``,
    advance ``last_seen_at``, FIFO-merge ``session_id`` into
    ``example_session_ids`` (capped at 5). ``first_seen_at`` is set ONLY by the
    INSERT clause and is never touched by the DO UPDATE branch. A NULL
    ``embedding`` (embedder unavailable for this sighting) never erases a
    previously stored vector — such a conflict can only come from an
    exact-hash match, so the stored embedding still describes the text.
    """
    ts = now or utc_now_iso()
    blob = serialize_embedding(embedding) if embedding is not None else None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT example_session_ids FROM repeated_request_signals WHERE request_hash = ?",
            (request_hash,),
        ).fetchone()
        if row is None:
            example_ids = [session_id]
        else:
            example_ids = _fifo_merge(json.loads(row["example_session_ids"]), session_id)

        conn.execute(
            """
            INSERT INTO repeated_request_signals
                (request_hash, project_id, session_kind, representative_text,
                 embedding, occurrence_count, example_session_ids,
                 first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(request_hash) DO UPDATE SET
                occurrence_count = occurrence_count + 1,
                last_seen_at = excluded.last_seen_at,
                example_session_ids = excluded.example_session_ids,
                representative_text = excluded.representative_text,
                embedding = COALESCE(excluded.embedding, embedding)
            """,
            (
                request_hash,
                project_id,
                session_kind,
                representative_text,
                blob,
                json.dumps(example_ids),
                ts,
                ts,
            ),
        )
        conn.commit()


def _row_to_model(row) -> RepeatedRequestSignal:
    emb = row["embedding"]
    return RepeatedRequestSignal(
        request_hash=row["request_hash"],
        project_id=row["project_id"],
        session_kind=row["session_kind"],
        representative_text=row["representative_text"],
        embedding=deserialize_embedding(emb) if emb is not None else None,
        occurrence_count=row["occurrence_count"],
        verified_success_count=row["verified_success_count"],
        example_session_ids=json.loads(row["example_session_ids"]),
        skill_created=bool(row["skill_created"]),
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
    )


def get_signal(request_hash: str) -> RepeatedRequestSignal | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM repeated_request_signals WHERE request_hash = ?",
            (request_hash,),
        ).fetchone()
        return _row_to_model(row) if row else None


def list_signals(
    project_id: str | None = None,
    session_kind: str | None = None,
    limit: int | None = None,
) -> list[RepeatedRequestSignal]:
    clauses: list[str] = []
    params: list[object] = []
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    if session_kind is not None:
        clauses.append("session_kind = ?")
        params.append(session_kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    # Rows are ordered most-salient-first, so a LIMIT keeps the highest-signal
    # candidates and bounds the cosine batch the detector runs on the bus thread.
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(int(limit))

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM repeated_request_signals"
            f"{where} ORDER BY occurrence_count DESC, last_seen_at DESC{limit_sql}",
            params,
        ).fetchall()
        return [_row_to_model(r) for r in rows]


def mark_skill_created(request_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE repeated_request_signals SET skill_created = 1 WHERE request_hash = ?",
            (request_hash,),
        )
        conn.commit()


def increment_verified_success(request_hash: str, by: int = 1) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE repeated_request_signals "
            "SET verified_success_count = verified_success_count + ? "
            "WHERE request_hash = ?",
            (by, request_hash),
        )
        conn.commit()
