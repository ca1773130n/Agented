"""Competitor-strategy DAO (v0.9.0 phase 26, competitor-strategy loop — P4).

Thin raw-SQLite persistence for the competitor-strategy HITL queue (migration
174, ``competitor_strategy``). This is the Wave-1 root the rest of phase 26
builds on: the generation service (26-02) writes proposals via
:func:`create_strategy`; the HITL routes (26-03) read via
:func:`list_strategies` / :func:`get_strategy`, drive the operator verdict via
:func:`set_status`, edit via :func:`update_body`, affirm the legal checklist via
:func:`record_legal_item`, and promote via :func:`mark_implementing`; the
materialize path (26-04) re-enforces the gate through :func:`mark_implementing`
and stamps ``plan_id``.

Conventions (per ``app/db/connection.py`` + repo rules):

- All DB access goes through :func:`app.db.connection.get_connection` (raw
  SQLite, ``sqlite3.Row`` factory). The context manager is rollback-on-error;
  the CALLER (here, each DAO function) commits explicitly.
- Ids are minted with ``generate_id("cstr-", 6)`` (the prefix carries its own
  dash; 6 random chars).
- ``signal_ids`` and ``legal_checklist`` are stored as JSON strings; the DAO
  ``json.dumps``-es on write and ``json.loads``-es on read (best-effort — a
  malformed blob degrades to the raw string rather than raising).

§5B LEGAL GATE — NON-BYPASSABLE, lives HERE in the DAO (not only a route):

- :func:`record_legal_item` merges one item into ``legal_checklist`` and sets
  ``legal_cleared_at`` = ``CURRENT_TIMESTAMP`` ONLY when ALL 7
  :data:`LEGAL_CHECKLIST_ITEMS` are affirmed true; otherwise it NULLs it.
- :func:`mark_implementing` is the HARD GATE: it re-reads the row and RAISES
  :class:`LegalGateNotCleared` whenever ``legal_cleared_at`` is NULL — it never
  mutates ``status``. No route or service can reach ``'implementing'`` without
  clearance because the only path through ``approved`` → ``implementing`` is
  this function.
- Edit-resets-clearance: :func:`update_body` flips ``independent_authorship`` +
  ``no_copied_code`` back to false and NULLs ``legal_cleared_at`` — any plan
  edit forces re-affirmation.

This module is deliberately thin: NO LLM calls and NO route logic live here.
"""

import json
from typing import Optional

from .connection import get_connection
from .ids import generate_id

# The 7 §5B clean-room / freedom-to-operate items an operator must affirm before
# any implement step. Canonical source for both this constant AND the i18n labels
# (26-03 derives the UI keys from this list). Order is meaningful only as the
# operator-facing checklist order; clearance requires ALL 7 true.
LEGAL_CHECKLIST_ITEMS: tuple = (
    "clean_room",
    "no_copied_code",
    "independent_authorship",
    "license_review",
    "patent_fto",
    "trademark_clear",
    "no_confidential_source",
)

# The subset reset to false on any body edit (re-affirmation after a plan change).
_EDIT_RESET_ITEMS: tuple = ("independent_authorship", "no_copied_code")

# Sentinel stamped into ``session_id`` by :func:`claim_for_autoimplement` to mark
# a strategy as CLAIMED for an in-flight auto-implement launch BEFORE any side
# effect (worktree / session) is created. The atomic claim flips a NULL
# ``session_id`` to this sentinel under a single conditional UPDATE; the caller
# replaces it with the real session id once the launch succeeds, or reverts it to
# NULL on failure. It is never a valid real session id (psess-…), so it is
# unambiguous as a claim marker.
AUTOIMPLEMENT_CLAIM_SENTINEL = "claiming"

# Allowed status transitions for the HITL state machine. ``approved`` →
# ``implementing`` is listed here, but the move is additionally gated by the
# legal clearance check in :func:`mark_implementing` — :func:`set_status` must
# never be used to bypass that gate (it routes ``approved`` → ``implementing``
# through :func:`mark_implementing`).
_ALLOWED_TRANSITIONS: dict = {
    "proposed": {"approved", "rejected"},
    "approved": {"implementing", "rejected"},
    "rejected": set(),
    "implementing": {"done"},
    "done": set(),
}


class LegalGateNotCleared(Exception):
    """Raised by :func:`mark_implementing` when ``legal_cleared_at`` is NULL.

    The §5B legal gate is enforced in the DAO so it is non-bypassable: a strategy
    cannot transition ``approved`` → ``implementing`` (and therefore can never be
    materialized into a ProjectPlan) until all 7 :data:`LEGAL_CHECKLIST_ITEMS`
    are affirmed. The service/route layer maps this to a 409.
    """


def _row_to_dict(row) -> Optional[dict]:
    """Convert a ``sqlite3.Row`` to a plain dict, parsing the JSON columns.

    ``signal_ids`` and ``legal_checklist`` are ``json.loads``-ed; a malformed /
    non-JSON blob degrades to the raw stored string instead of raising — a bad
    blob must never break a read.
    """
    if row is None:
        return None
    data = dict(row)
    for key in ("signal_ids", "legal_checklist"):
        raw = data.get(key)
        if raw is not None:
            try:
                data[key] = json.loads(raw)
            except (ValueError, TypeError):
                data[key] = raw
    return data


def _all_items_affirmed(checklist: dict) -> bool:
    """True only when every one of the 7 canonical items is stored as ``True``.

    Uses ``is True`` (never truthiness): a stored ``"true"``/``"1"``/``1`` must
    NOT count as an affirmation, so ``legal_cleared_at`` can never be set unless
    all 7 items are literally Python ``True``.
    """
    return all(checklist.get(item) is True for item in LEGAL_CHECKLIST_ITEMS)


def create_strategy(
    project_id: str,
    *,
    signal_ids: Optional[list] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    backend_kind: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Insert a ``'proposed'`` competitor strategy and return it as a dict.

    ``signal_ids`` (the ``detected_signal`` ids this strategy synthesizes) is
    ``json.dumps``-ed on write. ``legal_checklist`` starts NULL and
    ``legal_cleared_at`` starts NULL — clearance is earned only via
    :func:`record_legal_item`. The id is minted ``cstr-`` + 6.
    """
    strategy_id = generate_id("cstr-", 6)
    signal_ids_json = json.dumps(signal_ids) if signal_ids is not None else None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO competitor_strategy (
                id, project_id, signal_ids, title, body, backend_kind, model, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed')
            """,
            (strategy_id, project_id, signal_ids_json, title, body, backend_kind, model),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM competitor_strategy WHERE id = ?", (strategy_id,)
        ).fetchone()
    return _row_to_dict(row)


def list_strategies(project_id: str, *, statuses: Optional[list] = None) -> list:
    """Return a project's strategies, newest first (``created_at DESC``).

    ``statuses`` optionally filters to the given status values (default: all).
    Project-scoped — a foreign project's rows are never returned. ``rowid DESC``
    is a deterministic tiebreaker so two rows minted within the same
    ``CURRENT_TIMESTAMP`` second (which is only second-precise) still order by
    true insertion order rather than arbitrarily.
    """
    sql = "SELECT * FROM competitor_strategy WHERE project_id = ?"  # noqa: S608 (params bound)
    params: list = [project_id]
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        sql += f" AND status IN ({placeholders})"
        params.extend(statuses)
    sql += " ORDER BY created_at DESC, rowid DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_strategy(strategy_id: str, *, project_id: Optional[str] = None) -> Optional[dict]:
    """Return a single strategy row as a dict, or None if it does not exist.

    When ``project_id`` is supplied the lookup is project-scoped
    (``WHERE id = ? AND project_id = ?``) so a strategy belonging to another
    project returns None — the IDOR guard for the route layer.
    """
    sql = "SELECT * FROM competitor_strategy WHERE id = ?"
    params: list = [strategy_id]
    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return _row_to_dict(row)


def set_session_id(
    strategy_id: str, session_id: str, *, project_id: Optional[str] = None
) -> Optional[dict]:
    """Stamp the goal-loop ``session_id`` the auto-implement seam launched.

    Project-SCOPED when ``project_id`` is supplied (``WHERE id = ? AND
    project_id = ?``) so a foreign strategy is never mutated — the IDOR guard.
    This is the ONLY writer of ``session_id``, and 26-05 only reaches it behind
    the triple gate (flag + cleared §5B legal gate + confirm token). Returns the
    updated row, or None if no such (scoped) strategy exists.
    """
    current = get_strategy(strategy_id, project_id=project_id)
    if current is None:
        return None
    scope = " AND project_id = ?" if project_id is not None else ""
    params: list = [session_id, strategy_id]
    if project_id is not None:
        params.append(project_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy "
            "SET session_id = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?{scope}",
            params,
        )
        conn.commit()
    return get_strategy(strategy_id, project_id=project_id)


def claim_for_autoimplement(strategy_id: str, project_id: str) -> Optional[dict]:
    """ATOMICALLY claim a strategy for an auto-implement launch — fail CLOSED.

    The §5B / materialization gate and the side-effecting launch (worktree +
    session) happen at two different instants; a concurrent ``update_body`` /
    legal-reset between a naive read and the launch could start an agent past an
    invalidated gate (TOCTOU). This is the single ATOMIC chokepoint that closes
    that window: a single conditional UPDATE stamps the
    :data:`AUTOIMPLEMENT_CLAIM_SENTINEL` into ``session_id`` ONLY when the strategy
    is, AT WRITE TIME, still fully eligible —

    - belongs to ``project_id``;
    - ``status == 'implementing'`` (materialize already promoted it through the
      non-bypassable ``mark_implementing`` legal gate);
    - ``legal_cleared_at IS NOT NULL`` (§5B cleared);
    - ``plan_id IS NOT NULL`` (materialized into a ProjectPlan);
    - ``session_id IS NULL`` (not already claimed / launched).

    Returns the claimed row when exactly one row matched (the caller may now
    create the worktree + session, then call :func:`set_session_id` to replace the
    sentinel with the real id); returns ``None`` when the claim matched nothing —
    the gate was invalidated, the strategy was already claimed, or it is not in a
    launchable state. The caller MUST create NO side effect on ``None``.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE competitor_strategy "
            "SET session_id = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND status = 'implementing' "
            "AND legal_cleared_at IS NOT NULL AND plan_id IS NOT NULL "
            "AND session_id IS NULL",
            (AUTOIMPLEMENT_CLAIM_SENTINEL, strategy_id, project_id),
        )
        rowcount = cur.rowcount
        conn.commit()
    if rowcount == 1:
        return get_strategy(strategy_id, project_id=project_id)
    return None


def release_autoimplement_claim(strategy_id: str, project_id: str) -> Optional[dict]:
    """Revert an auto-implement claim — clear the sentinel back to NULL.

    Called when the post-claim launch (worktree create / create_session / start)
    fails: it un-claims the strategy so it is re-claimable, but ONLY when the
    ``session_id`` still holds the :data:`AUTOIMPLEMENT_CLAIM_SENTINEL` (never
    clears a real, successfully-stamped session id). Returns the updated row, or
    None if no such (scoped) strategy exists.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy "
            "SET session_id = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND project_id = ? AND session_id = ?",
            (strategy_id, project_id, AUTOIMPLEMENT_CLAIM_SENTINEL),
        )
        conn.commit()
    return get_strategy(strategy_id, project_id=project_id)


def set_status(
    strategy_id: str, status: str, *, project_id: Optional[str] = None
) -> Optional[dict]:
    """Set a strategy's ``status`` after validating the transition.

    Allowed moves: ``proposed`` → ``approved``/``rejected``; ``approved`` →
    ``rejected`` (and ``implementing`` ONLY via :func:`mark_implementing`, the
    legal gate); ``implementing`` → ``done``. An illegal jump raises
    ``ValueError`` and mutates nothing. Returns the updated row, or None if no
    such (scoped) strategy exists.

    NOTE: ``approved`` → ``implementing`` is intentionally rejected here — that
    promotion MUST go through :func:`mark_implementing` so the §5B legal gate
    cannot be bypassed via a raw status write.
    """
    current = get_strategy(strategy_id, project_id=project_id)
    if current is None:
        return None
    if status == "implementing":
        raise ValueError("approved->implementing must go through mark_implementing (legal gate)")
    # In-flight guard (fail CLOSED): never mutate the status of a strategy that is
    # mid-claim (session_id == the claim sentinel). The legitimate
    # ``implementing`` -> ``done`` completion happens only AFTER the real
    # session_id is stamped (sentinel replaced), so a sentinel here means a launch
    # is in progress and the status must not move under it.
    if current.get("session_id") == AUTOIMPLEMENT_CLAIM_SENTINEL:
        raise ValueError(
            "cannot change status while an auto-implement launch is in flight (strategy is claimed)"
        )
    allowed = _ALLOWED_TRANSITIONS.get(current["status"], set())
    if status not in allowed:
        raise ValueError(f"illegal status transition {current['status']!r} -> {status!r}")
    scope = " AND project_id = ?" if project_id is not None else ""
    params: list = [status, strategy_id]
    if project_id is not None:
        params.append(project_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy "
            "SET status = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?{scope}",
            params,
        )
        conn.commit()
    return get_strategy(strategy_id, project_id=project_id)


def update_body(
    strategy_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[dict]:
    """Operator edit of a proposed/approved proposal — RESETS legal clearance.

    Edit-resets-clearance (§5B): any body edit flips ``independent_authorship``
    + ``no_copied_code`` back to false in ``legal_checklist`` and NULLs
    ``legal_cleared_at``, forcing re-affirmation before the strategy can be
    implemented again. ``title``/``body`` are each updated only when provided
    (None leaves the column unchanged). Returns the updated row, or None if no
    such (scoped) strategy exists.
    """
    current = get_strategy(strategy_id, project_id=project_id)
    if current is None:
        return None
    # In-flight guard (fail CLOSED): an auto-implement loop may already be running
    # against this strategy (status 'implementing', or session_id claimed/stamped).
    # A body edit NULLs ``legal_cleared_at`` — letting it run here would reset the
    # §5B clearance OUT FROM UNDER a live agent (TOCTOU on the launch gate). Refuse.
    if current["status"] == "implementing" or current.get("session_id"):
        raise ValueError(
            "cannot edit a strategy that is implementing or has an auto-implement "
            "session — clearance reset under a running loop is forbidden"
        )
    checklist = current.get("legal_checklist")
    if not isinstance(checklist, dict):
        checklist = {}
    for item in _EDIT_RESET_ITEMS:
        checklist[item] = False
    new_title = current["title"] if title is None else title
    new_body = current["body"] if body is None else body
    scope = " AND project_id = ?" if project_id is not None else ""
    params: list = [new_title, new_body, json.dumps(checklist), strategy_id]
    if project_id is not None:
        params.append(project_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy "
            "SET title = ?, body = ?, legal_checklist = ?, "
            "legal_cleared_at = NULL, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?{scope}",
            params,
        )
        conn.commit()
    return get_strategy(strategy_id, project_id=project_id)


def record_legal_item(
    strategy_id: str,
    item_key: str,
    value: bool,
    *,
    project_id: Optional[str] = None,
) -> Optional[dict]:
    """Affirm/deny one §5B checklist item; set ``legal_cleared_at`` at 7/7.

    ``item_key`` must be one of :data:`LEGAL_CHECKLIST_ITEMS` (else ValueError).
    The value is merged into ``legal_checklist`` JSON and ``updated_at`` bumped.
    If ALL 7 items are now true, ``legal_cleared_at`` is set to
    ``CURRENT_TIMESTAMP``; otherwise it is NULLed (a later deny re-locks the
    gate). Returns the updated row, or None if no such (scoped) strategy exists.
    """
    if item_key not in LEGAL_CHECKLIST_ITEMS:
        raise ValueError(f"unknown legal checklist item: {item_key!r}")
    current = get_strategy(strategy_id, project_id=project_id)
    if current is None:
        return None
    # In-flight guard (fail CLOSED): denying an item NULLs ``legal_cleared_at``,
    # which would reset the §5B gate under a running auto-implement loop. Refuse
    # any legal-checklist write once the strategy is implementing / claimed.
    if current["status"] == "implementing" or current.get("session_id"):
        raise ValueError(
            "cannot change the legal checklist of a strategy that is implementing "
            "or has an auto-implement session — clearance reset under a running "
            "loop is forbidden"
        )
    checklist = current.get("legal_checklist")
    if not isinstance(checklist, dict):
        checklist = {}
    # §5B gate: store ONLY a real bool. A truthy non-bool ("false", "0", 1, …)
    # must never be coerced to True — affirmation counts ``is True`` downstream,
    # and an item is affirmed only when the caller passes Python ``True``.
    checklist[item_key] = value is True
    cleared = _all_items_affirmed(checklist)
    cleared_clause = "CURRENT_TIMESTAMP" if cleared else "NULL"
    scope = " AND project_id = ?" if project_id is not None else ""
    params: list = [json.dumps(checklist), strategy_id]
    if project_id is not None:
        params.append(project_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy "
            f"SET legal_checklist = ?, legal_cleared_at = {cleared_clause}, "
            "updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?{scope}",
            params,
        )
        conn.commit()
    return get_strategy(strategy_id, project_id=project_id)


def mark_implementing(strategy_id: str, *, project_id: Optional[str] = None) -> dict:
    """The HARD §5B legal gate: ``approved`` → ``implementing`` only when cleared.

    Re-reads the row and:

    - raises ``ValueError`` if it does not exist or its status is not
      ``'approved'`` (status is NEVER mutated on this path);
    - raises :class:`LegalGateNotCleared` if ``legal_cleared_at`` IS NULL — the
      non-bypassable block (no status mutation);
    - only when cleared, sets ``status = 'implementing'`` and returns the row.

    This is the single chokepoint into ``implementing`` — the materialize path
    (26-04) calls it before creating a ProjectPlan, so an uncleared strategy can
    never produce a plan.
    """
    scope = " AND project_id = ?" if project_id is not None else ""
    params: list = [strategy_id]
    if project_id is not None:
        params.append(project_id)
    # Single ATOMIC conditional UPDATE — the gate check and the write happen in
    # one statement, so a concurrent update_body/record_legal_item cannot slip
    # between a TOCTOU check and the write to violate the §5B gate. The row only
    # flips to 'implementing' when it is still 'approved' AND legal_cleared_at is
    # set at write time.
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE competitor_strategy "
            "SET status = 'implementing', updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ? AND status = 'approved' AND legal_cleared_at IS NOT NULL{scope}",
            params,
        )
        rowcount = cur.rowcount
        conn.commit()
    if rowcount == 1:
        return get_strategy(strategy_id, project_id=project_id)
    # The atomic UPDATE matched nothing — re-READ (no mutation) to raise the
    # precise existing exception for the operator.
    current = get_strategy(strategy_id, project_id=project_id)
    if current is None:
        raise ValueError(f"strategy not found: {strategy_id!r}")
    if current["status"] != "approved":
        raise ValueError(f"mark_implementing requires status 'approved', got {current['status']!r}")
    if current["legal_cleared_at"] is None:
        raise LegalGateNotCleared(
            f"strategy {strategy_id} cannot be implemented: §5B legal gate not cleared "
            "(all 7 checklist items must be affirmed)"
        )
    # Status is 'approved' and cleared yet 0 rows matched — only possible if the
    # row was concurrently mutated out from under us; treat as not-found.
    raise ValueError(f"strategy not found: {strategy_id!r}")
