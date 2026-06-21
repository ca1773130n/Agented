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
(score / reason / evidence / url + ``updated_at``) on conflict and NEVER touches
``source_id`` or an operator VERDICT (``dismissed`` / ``added``) — a re-scan must
not resurrect a ``dismissed`` / ``added`` candidate back to ``suggested``. The ONE
exception is the TRANSIENT ``claiming`` state (a promotion mid-flight, not a
verdict): a conflicting re-scan resets ``claiming`` → ``suggested`` so an abandoned
claim (process died between claim and complete/revert) is automatically un-stuck.

This module is deliberately thin: NO GitHub calls and NO ranking live here
(that is 24-02 / 24-03).
"""

import json
from typing import Optional

from .connection import get_connection
from .ids import generate_id


class PromotionInProgress(Exception):
    """A ``'claiming'`` row was hit by a mutation that must not clobber an in-flight claim.

    DAO-local signal (the DAO never imports the service, so it raises its OWN type):
    :func:`dismiss_suggestion` raises this when the conditional dismiss matches zero
    rows BECAUSE the row is mid-promotion (``status == 'claiming'``) rather than
    missing. The service catches it and re-raises ``PromotionConflict`` (route → 409
    "promotion in progress, retry"). Keeps the dismiss from flipping a ``'claiming'``
    row to ``'dismissed'`` and silently orphaning the promoter's just-added source.
    """


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
                -- 'claiming' is a TRANSIENT promotion state, not an operator verdict:
                -- reset it to 'suggested' on a re-scan so an abandoned claim (a process
                -- that died between claim and complete/revert, otherwise stuck 'claiming'
                -- and 409-ing every future accept) is automatically un-stuck. 'added' and
                -- 'dismissed' are real verdicts and stay sticky.
                status        = CASE
                                    WHEN status = 'claiming' THEN 'suggested'
                                    ELSE status
                                END,
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

    Flips ``status`` ``suggested`` → ``claiming`` in a SINGLE conditional UPDATE
    (``WHERE id = ? AND project_id = ? AND status = 'suggested'``) and returns
    whether THIS caller won the claim (exactly one row changed). Two concurrent
    accepts both read ``status == 'suggested'``, but only the first UPDATE matches
    the ``status = 'suggested'`` predicate — the loser changes zero rows and gets
    ``False`` — so ``add_source`` (which has no ``UNIQUE(project_id, url)``) never
    runs twice and the ``competitor_source`` row is never duplicated.

    The intermediate ``'claiming'`` state is the round-3 fix for the corrupt-loser
    race: it keeps ``status == 'added'`` an INVARIANT that ALWAYS implies a stamped
    ``source_id``. The winner only flips ``claiming`` → ``added`` AFTER ``add_source``
    has minted the id, stamping both in the single atomic UPDATE of
    :func:`complete_promotion`; a loser that re-reads in the window sees
    ``'claiming'`` (promotion in progress → 409, retry) instead of an ``'added'``
    row with a NULL ``source_id``.

    Project-scoped: a foreign-project id matches nothing and returns ``False``
    (the caller's not-found / 404 path handles it). A failed add reverts the claim
    via :func:`revert_promotion_claim`.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'claiming', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'suggested'",
            (suggestion_id, project_id),
        )
        claimed = cur.rowcount == 1
        conn.commit()
    return claimed


def complete_promotion(suggestion_id: str, project_id: str, source_id: str) -> Optional[dict]:
    """Finalize a won claim: ``claiming`` → ``added`` AND stamp ``source_id`` atomically.

    The other half of the round-3 invariant (``status == 'added'`` ALWAYS implies a
    stamped ``source_id``): only after ``add_source`` mints the competitor_source id
    does the winner flip the claimed row out of ``'claiming'``, setting ``status`` and
    ``source_id`` in ONE conditional UPDATE scoped to ``status = 'claiming'``. A
    concurrent loser therefore never observes ``'added'`` with a NULL ``source_id`` —
    it sees ``'claiming'`` (→ 409) until this atomic stamp lands.

    Returns the updated row when the stamp LANDED (``rowcount == 1`` — the winner
    still owned the ``'claiming'`` row). Returns ``None`` when the stamp matched ZERO
    rows — the claim was stolen/lost out from under the promoter (the row is no longer
    ``'claiming'``, e.g. it was reset by a re-scan or otherwise mutated). ``None`` is
    the COMPENSATE signal: the caller has already committed ``add_source``, so it MUST
    delete that orphaned ``competitor_source`` (the ``source_id`` it just passed) and
    raise — never leave a source with no suggestion link. With the conditional dismiss
    in place a stolen claim is unreachable in practice, but this is the safety net.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'added', source_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'claiming'",
            (source_id, suggestion_id, project_id),
        )
        stamped = cur.rowcount == 1
        conn.commit()
        if not stamped:
            # Claim lost/stolen — signal the caller to roll back the orphaned source.
            return None
        row = conn.execute(
            "SELECT * FROM discovery_suggestion WHERE id = ? AND project_id = ?",
            (suggestion_id, project_id),
        ).fetchone()
    return _row_to_dict(row)


def revert_promotion_claim(suggestion_id: str, project_id: str) -> None:
    """Undo a promotion claim — restore ``claiming`` → ``suggested`` and clear ``source_id``.

    The compensating action when :func:`claim_for_promotion` won but the
    subsequent ``add_source`` raised (BEFORE :func:`complete_promotion` could flip
    the row to ``'added'``): without this a failed add would leave a phantom
    ``'claiming'`` row that no loser could ever promote (it would 409 forever).
    Scoped to ``(id, project_id, status = 'claiming')`` so it only reverts a row
    still mid-claim — a winner that already stamped a real source (now ``'added'``)
    is out of the ``'claiming'`` window and is never reverted.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'suggested', source_id = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'claiming'",
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


def dismiss_suggestion(suggestion_id: str, project_id: str) -> Optional[dict]:
    """Dismiss a suggestion CONDITIONALLY so it can never clobber an in-flight claim.

    The concurrency fix for the dismiss-vs-promote race: ``set_status('dismissed')``
    did an UNCONDITIONAL UPDATE, so a dismiss racing a promotion could flip a
    ``'claiming'`` row to ``'dismissed'``; the promoter's :func:`complete_promotion`
    (``WHERE status='claiming'``) then matched ZERO rows silently while ``add_source``
    had already committed — leaving an orphaned ``competitor_source`` with no link.

    So the UPDATE is scoped to ``status IN ('suggested', 'added')`` — never
    ``'claiming'`` — and the outcome is disambiguated:

      * one row changed → return the updated row (dismissed; idempotent on ``'added'``
        and on an already-``'dismissed'`` row, both of which match the predicate);
      * zero rows changed AND the row exists under this project as ``'claiming'`` →
        raise :class:`PromotionInProgress` (the service maps it to a 409 — promotion
        in progress, retry) rather than silently clobbering the claim;
      * zero rows changed AND no such (id, project) row → return ``None`` (the
        existing project-scoped 404 path for a missing / foreign row).
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE discovery_suggestion "
            "SET status = 'dismissed', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status IN ('suggested', 'added')",
            (suggestion_id, project_id),
        )
        changed = cur.rowcount
        conn.commit()
        if changed == 0:
            # Distinguish "row is mid-claim" (409) from "row is missing/foreign" (404).
            existing = conn.execute(
                "SELECT status FROM discovery_suggestion WHERE id = ? AND project_id = ?",
                (suggestion_id, project_id),
            ).fetchone()
            if existing is not None and existing["status"] == "claiming":
                raise PromotionInProgress(
                    f"Suggestion {suggestion_id} is being promoted; cannot dismiss — retry shortly"
                )
            return None
        row = conn.execute(
            "SELECT * FROM discovery_suggestion WHERE id = ? AND project_id = ?",
            (suggestion_id, project_id),
        ).fetchone()
    return _row_to_dict(row)
