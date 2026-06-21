"""Discovery-suggestion DAO (v0.9.0 phase 24, agent-assisted discovery).

Thin raw-SQLite persistence for the competitor-discovery suggestion queue
(migration 172, ``discovery_suggestion``). This is the Wave-1 root the rest of
phase 24 builds on: the DiscoveryService fan-out (24-02) and ranking (24-03)
write candidates here via :func:`upsert_suggestion`; the scan / add / dismiss
routes (24-04) read via :func:`list_suggestions` / :func:`get_suggestion` and
mutate the operator's verdict via :func:`set_status`.

Conventions (per ``app/db/connection.py`` + repo rules):

- All DB access goes through :func:`app.db.connection.get_connection` (raw
  SQLite, ``sqlite3.Row`` factory). The context manager is rollback-on-error;
  the CALLER commits explicitly.
- Ids are minted with ``generate_id("dsug-", 8)`` (the prefix carries its own
  dash; 8 random chars).
- ``evidence`` is stored as a JSON string; a dict/list is ``json.dumps``-ed on
  write and ``json.loads``-ed on read (best-effort — malformed JSON degrades to
  the raw string rather than raising).

Idempotent-upsert invariant: :func:`upsert_suggestion` refreshes ranking data
(score / reason / evidence / url + ``updated_at``) on conflict but NEVER touches
``status`` or ``source_id`` — a re-scan must not resurrect a ``dismissed`` /
``added`` candidate back to ``suggested``.

This module is deliberately thin: NO GitHub calls and NO ranking live here
(that is 24-02 / 24-03).
"""

import json
from typing import Optional

from .connection import get_connection
from .ids import generate_id


def _serialize_evidence(evidence) -> Optional[str]:
    """Return a JSON string for ``evidence``, or None.

    A dict/list is dumped to JSON. A string is stored as-is (assumed already
    JSON / a plain reason blob). None stays None.
    """
    if evidence is None:
        return None
    if isinstance(evidence, str):
        return evidence
    return json.dumps(evidence)


def _row_to_dict(row) -> Optional[dict]:
    """Convert a ``sqlite3.Row`` to a plain dict, parsing ``evidence`` JSON.

    Malformed / non-JSON ``evidence`` degrades to the raw stored string instead
    of raising — a bad blob must never break a read.
    """
    if row is None:
        return None
    data = dict(row)
    raw = data.get("evidence")
    if raw is not None:
        try:
            data["evidence"] = json.loads(raw)
        except (ValueError, TypeError):
            data["evidence"] = raw
    return data


def upsert_suggestion(
    project_id: str,
    owner: str,
    repo: str,
    url: str,
    *,
    kind: str = "github_repo",
    score: Optional[float] = None,
    reason: Optional[str] = None,
    evidence=None,
    source_id: Optional[str] = None,
) -> dict:
    """Insert a discovery suggestion, or refresh it on the unique key.

    Conflict key is ``(project_id, candidate_owner, candidate_repo)``. On
    conflict the ranking columns (``score``, ``reason``, ``evidence``,
    ``candidate_url``) and ``updated_at`` are refreshed, but ``status`` and
    ``source_id`` are intentionally left untouched so an operator's
    dismiss/add verdict survives a re-scan.

    ``score`` is NULL-accepting — a missing score never blocks a suggestion.
    Returns the resulting row as a dict (``evidence`` parsed back from JSON).
    """
    evidence_json = _serialize_evidence(evidence)
    with get_connection() as conn:
        suggestion_id = generate_id("dsug-", 8)
        conn.execute(
            """
            INSERT INTO discovery_suggestion (
                id, project_id, candidate_owner, candidate_repo, candidate_url,
                kind, score, reason, evidence, source_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, candidate_owner, candidate_repo) DO UPDATE SET
                candidate_url = excluded.candidate_url,
                kind          = excluded.kind,
                score         = excluded.score,
                reason        = excluded.reason,
                evidence      = excluded.evidence,
                updated_at    = CURRENT_TIMESTAMP
            """,
            (
                suggestion_id,
                project_id,
                owner,
                repo,
                url,
                kind,
                score,
                reason,
                evidence_json,
                source_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM discovery_suggestion "
            "WHERE project_id = ? AND candidate_owner = ? AND candidate_repo = ?",
            (project_id, owner, repo),
        ).fetchone()
    return _row_to_dict(row)


def list_suggestions(project_id: str, *, statuses: Optional[list] = None) -> list:
    """Return a project's suggestions, highest-scored first.

    Ordered by ``score DESC`` with NULL scores last, then ``created_at DESC``.
    ``statuses`` optionally filters to the given status values (default: all).
    Each row's ``evidence`` is parsed back from JSON.
    """
    sql = "SELECT * FROM discovery_suggestion WHERE project_id = ?"  # noqa: S608 (params bound below)
    params: list = [project_id]
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        sql += f" AND status IN ({placeholders})"
        params.extend(statuses)
    # NULLS LAST is portable across SQLite versions via the "score IS NULL" key.
    sql += " ORDER BY score IS NULL, score DESC, created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def claim_for_promotion(suggestion_id: str, project_id: str) -> bool:
    """Atomically claim a ``suggested`` row for promotion (the concurrent-accept guard).

    Flips ``status`` ``suggested`` → ``added`` in a SINGLE conditional UPDATE
    (``WHERE id = ? AND project_id = ? AND status = 'suggested'``) and returns
    whether THIS caller won the claim (exactly one row changed). Two concurrent
    accepts both read ``status == 'suggested'``, but only the first UPDATE matches
    the ``status = 'suggested'`` predicate — the loser changes zero rows and gets
    ``False`` — so ``add_source`` (which has no ``UNIQUE(project_id, url)``) never
    runs twice and the ``competitor_source`` row is never duplicated.

    Project-scoped: a foreign-project id matches nothing and returns ``False``
    (the caller's not-found / 404 path handles it). ``source_id`` is stamped by a
    follow-up scoped UPDATE once ``add_source`` has minted the id (see
    :func:`set_status`); a failed add reverts the claim via
    :func:`revert_promotion_claim`.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'added', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'suggested'",
            (suggestion_id, project_id),
        )
        claimed = cur.rowcount == 1
        conn.commit()
    return claimed


def revert_promotion_claim(suggestion_id: str, project_id: str) -> None:
    """Undo a promotion claim — restore ``added`` → ``suggested`` and clear ``source_id``.

    The compensating action when :func:`claim_for_promotion` won but the
    subsequent ``add_source`` raised: without this a failed add would leave a
    phantom ``added`` row with no backing ``competitor_source``. Scoped to
    ``(id, project_id, status = 'added')`` so it only reverts a row this flow
    actually claimed (a concurrent winner that already stamped a real source is
    not in the ``added``-with-the-same-context window we revert).
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'suggested', source_id = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'added'",
            (suggestion_id, project_id),
        )
        conn.commit()


def get_suggestion(suggestion_id: str, *, project_id: Optional[str] = None) -> Optional[dict]:
    """Return a single suggestion row as a dict, or None if it does not exist.

    When ``project_id`` is supplied the lookup is project-scoped
    (``WHERE id = ? AND project_id = ?``) so a suggestion belonging to another
    project returns None — the IDOR guard for the accept/dismiss path (a caller
    with access to project A must not reach a suggestion seeded under project B
    by pairing A's URL with B's id). Omitting ``project_id`` keeps the unscoped
    read for internal callers that already trust the id.
    """
    sql = "SELECT * FROM discovery_suggestion WHERE id = ?"
    params: list = [suggestion_id]
    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return _row_to_dict(row)


def set_status(
    suggestion_id: str,
    status: str,
    *,
    project_id: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Optional[dict]:
    """Set a suggestion's ``status`` (and optionally stamp ``source_id``).

    Used by the add/dismiss routes (24-04): ``add`` flips status to ``added``
    and stamps the promoted ``competitor_source`` id; ``dismiss`` flips status
    to ``dismissed``. ``updated_at`` is always bumped. Returns the updated row
    as a dict, or None if no such suggestion exists.

    When ``project_id`` is supplied the mutation is project-scoped
    (``WHERE id = ? AND project_id = ?``) and a foreign-project id is a no-op
    that returns None — closing the IDOR where a caller authorized for project A
    flips a suggestion owned by project B.
    """
    scope = " AND project_id = ?" if project_id is not None else ""
    with get_connection() as conn:
        if source_id is not None:
            params: list = [status, source_id, suggestion_id]
            if project_id is not None:
                params.append(project_id)
            conn.execute(
                "UPDATE discovery_suggestion "
                "SET status = ?, source_id = ?, updated_at = CURRENT_TIMESTAMP "
                f"WHERE id = ?{scope}",
                params,
            )
        else:
            params = [status, suggestion_id]
            if project_id is not None:
                params.append(project_id)
            conn.execute(
                "UPDATE discovery_suggestion "
                "SET status = ?, updated_at = CURRENT_TIMESTAMP "
                f"WHERE id = ?{scope}",
                params,
            )
        conn.commit()
        sel_sql = "SELECT * FROM discovery_suggestion WHERE id = ?"
        sel_params: list = [suggestion_id]
        if project_id is not None:
            sel_sql += " AND project_id = ?"
            sel_params.append(project_id)
        row = conn.execute(sel_sql, sel_params).fetchone()
    return _row_to_dict(row)
