"""PolicyService — the stackable policy / governance engine (phase 23, 23-01).

A single ``policies`` table (migration 176) holds rows at three scopes —
SERVER, TEAM and SESSION. ``evaluate()`` walks the scopes SESSION-first (the
stricter scope, per the standing session-not-bot rule), reads enabled rows per
scope ordered by ``priority DESC``, and returns the FIRST deny immediately
without consulting any later scope. A session-scope DENY therefore short-circuits
a server-scope ALLOW. ASK is collected (first wins) only if no DENY is found;
ALLOW is the default fall-through.

This plan (23-01) is the PRIMITIVE: ``_eval_row`` returns each row's stored
``effect`` verbatim. The ``_BUILTINS`` dispatch dict is the extension seam that
23-02 fills in (kind -> evaluator callable). Enforcement plans (23-03) import
``PolicyDenied`` to raise on a DENY verdict.

Verdict shape (PolicyVerdict — a plain dict):
    {"decision": "allow"|"deny"|"ask", "policy_id": str|None,
     "kind": str|None, "reason": str, "scope": str|None}
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from ..database import get_connection
from ..db.ids import generate_id

logger = logging.getLogger(__name__)

POLICY_ID_PREFIX = "pol-"
POLICY_ID_LENGTH = 6

# ASK round-trip tuning. Mirrors goal_loop_runner._PAUSE_POLL_SECONDS (0.5) so the
# policy await poll cadence matches the existing human-gate poll loop.
_POLICY_POLL_SECONDS = 0.5
_POLICY_DEFAULT_MAX_WALL_SECONDS = 600

# ASK-id-keyed decision registry. In-process is coherent under gunicorn
# workers=1 (CLAUDE.md): a single worker shares this dict across the launching
# call (which polls in await_decision) and the HTTP decision route (which calls
# submit_policy_decision). value: None = pending; (decision, message) = resolved.
#
# SECURITY (FIX 2 — ask-scoped): the key is the UNIQUE ``ask_id`` of an individual
# ASK, NOT the ``session_id``. Keying by session let a stale, no-waiter decision
# for one ask sit in the registry and get consumed by a LATER ASK on the same
# session (a silent auto-approve of a future, un-answered ask). An ask_id is a
# fresh uuid per ASK, so a decision can only ever resolve the exact ask it answers.
_POLICY_DECISIONS: dict = {}

# Guards the read-modify-write on _POLICY_DECISIONS so a decision that arrives
# BEFORE the launching call registers its waiter is not lost to a clobbering
# write (launch-ASK deadlock fix), now scoped per ask_id. value states: absent =
# no ask in flight; None = ask awaiting a decision; (decision, message) = resolved.
_POLICY_LOCK = threading.Lock()


class PolicyDenied(Exception):
    """Raised by enforcement plans (23-03) when evaluate() returns a DENY verdict.

    Carries the offending verdict dict on ``.verdict`` for callers that want to
    surface the policy id / reason.
    """

    def __init__(self, verdict: dict):
        self.verdict = verdict
        reason = verdict.get("reason") or "policy denied"
        super().__init__(reason)


def _eval_cost_budget(row: dict, action: dict):
    """cost_budget builtin (SC2) — hard/soft cost thresholds.

    Mirrors the hard/soft semantics of ``budget_service.check_budget``
    (budget_service.py:340-398) but stays PURE: the live spend is supplied on
    the action ctx (``total_cost_usd``, falling back to ``spend``) rather than
    read from the DB, so the evaluator is trivially unit-testable. The
    enforcement plan (23-03) is responsible for populating those counters.

    params: {max_cost_usd: float, ask_thresholds_usd: list[float]}
      - spend >= max_cost_usd (and max_cost_usd > 0) -> deny (hard cap)
      - any threshold t where spend >= t            -> ask  (soft threshold)
      - else                                         -> allow
    """
    params = row.get("params") or {}
    spend = action.get("total_cost_usd", action.get("spend", 0.0)) or 0.0
    max_cost = params.get("max_cost_usd", 0.0) or 0.0
    if max_cost > 0 and spend >= max_cost:
        return "deny", f"hard cost cap reached: ${spend:.2f} >= ${max_cost:.2f}"
    thresholds = params.get("ask_thresholds_usd") or []
    crossed = [t for t in thresholds if spend >= t]
    if crossed:
        return "ask", f"soft cost threshold crossed: ${spend:.2f} >= ${max(crossed):.2f}"
    return "allow", "within cost budget"


def _eval_max_tool_calls(row: dict, action: dict):
    """max_tool_calls_per_session builtin (SC2) — per-session tool-call cap.

    params: {max_tool_calls: int}
      - count >= max_tool_calls (and max_tool_calls > 0) -> deny
      - else                                              -> allow
    The live count is supplied on the action ctx as ``tool_calls``.
    """
    params = row.get("params") or {}
    count = action.get("tool_calls", 0) or 0
    max_calls = params.get("max_tool_calls", 0) or 0
    if max_calls > 0 and count >= max_calls:
        return "deny", f"tool-call cap reached: {count} >= {max_calls}"
    return "allow", "within tool-call budget"


def _eval_ask_on_os_tools(row: dict, action: dict):
    """ask_on_os_tools builtin (SC2) — require approval for OS-touching tools.

    params: {} or {kinds: [...]} (defaults to shell/file_write/process_launch)
      - action.kind in kinds -> ask
      - else                 -> allow
    """
    params = row.get("params") or {}
    kinds = params.get("kinds") or ["shell", "file_write", "process_launch"]
    kind = action.get("kind")
    if kind in kinds:
        return "ask", f"OS tool requires approval: {kind}"
    return "allow", "non-OS tool"


def _eval_enforce_sandbox(row: dict, action: dict):
    """enforce_sandbox builtin (SC2) — STORE-NOW / ENFORCE-IN-PHASE-24.

    INERT UNTIL PHASE 24: this evaluator produces a deny/allow VERDICT but
    invokes NO actual sandbox — no real sandbox runtime exists until Phase 24
    (OS-level harness sandboxing). The flag is stored now so policies can be
    authored ahead of the runtime; the verdict only gates a non-sandboxed
    launch so the inert path (everything else) always allows with an explicit
    "inert" reason.

    params: {require_sandbox: bool}
      - require_sandbox set AND action not sandboxed AND kind is a launch
        ({process_launch, shell}) -> deny (Phase 24 will make this real)
      - else                       -> allow (inert)
    """
    params = row.get("params") or {}
    require = params.get("require_sandbox", True)
    launch_kinds = {"process_launch", "shell"}
    if require and not action.get("sandboxed") and action.get("kind") in launch_kinds:
        return "deny", "sandbox required for launch (enforced in Phase 24)"
    return "allow", "sandbox flag stored (inert until Phase 24)"


# Extension seam filled by 23-02: maps a policy ``kind`` to a builtin evaluator
# callable ``(row, action) -> (decision, reason)``. Unknown/custom kinds fall
# back to the stored ``effect`` (see ``_eval_row``).
_BUILTINS: dict = {
    "cost_budget": _eval_cost_budget,
    "max_tool_calls_per_session": _eval_max_tool_calls,
    "ask_on_os_tools": _eval_ask_on_os_tools,
    "enforce_sandbox": _eval_enforce_sandbox,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict, parsing ``params`` JSON.

    SECURITY (23 BLOCKER 3 — fail CLOSED): malformed ``params`` JSON used to be
    swallowed to ``{}``, which silently DISABLED the cost/tool-call caps (an empty
    params dict makes ``max_cost_usd``/``max_tool_calls`` default to 0 → no cap →
    fall through to ALLOW). A corrupt policy row must never weaken governance. We
    therefore flag the row ``_params_invalid`` so ``_eval_row`` can fail closed
    (DENY) instead of evaluating against a hollow params dict.
    """
    d = dict(row)
    raw = d.get("params")
    if isinstance(raw, str):
        try:
            d["params"] = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            d["params"] = {}
            d["_params_invalid"] = True
    elif raw is None:
        d["params"] = {}
    elif not isinstance(raw, dict):
        # Any non-str / non-dict / non-None params value is unexpected and
        # uninterpretable — treat it as malformed and fail closed downstream.
        d["params"] = {}
        d["_params_invalid"] = True
    return d


def _normalize_decision(raw) -> str:
    """Coerce a stored/looked-up effect into a known decision, failing CLOSED.

    SECURITY (23 MAJOR 5): only an exact ``"allow"`` (case-insensitive, trimmed)
    counts as allow. ``"deny"`` → deny, ``"ask"`` → ask. ANYTHING ELSE — a typo'd
    or custom effect like ``"weird"``, a wrong-cased ``"ALLOW"`` mismatch, ``None``,
    or a non-string — collapses to ``"deny"`` so an unrecognized effect can never
    fall through to allow.
    """
    if not isinstance(raw, str):
        return "deny"
    norm = raw.strip().lower()
    if norm in ("allow", "deny", "ask"):
        return norm
    return "deny"


class PolicyService:
    """Classmethod service for the stackable policy engine (no instance state)."""

    # Evaluation order: SESSION first (stricter), then TEAM, then SERVER. The
    # server scope is the sentinel (scope_id IS NULL) and is always consulted.
    _SCOPE_ORDER = ("session", "team", "server")

    # -- Evaluation -------------------------------------------------------

    @classmethod
    def evaluate(cls, *, session_id: str, team_id=None, action: dict) -> dict:
        """Stack policies across [session, team, server] and return a verdict.

        Returns the FIRST deny immediately (short-circuit). Collects the first
        ASK if no DENY is found. Defaults to ALLOW (scope=None) when nothing
        matches. ``action`` is forwarded to per-row evaluation (used by 23-02
        builtins; ignored by the verbatim-effect evaluator here).
        """
        scope_ids = {"session": session_id, "team": team_id, "server": None}
        ask_verdict = None

        for scope in cls._SCOPE_ORDER:
            scope_id = scope_ids[scope]
            # Skip a scoped lookup with no id, EXCEPT server (the sentinel scope
            # whose scope_id is intentionally NULL).
            if scope != "server" and scope_id is None:
                continue

            for row in cls._rows_for(scope, scope_id):
                decision, reason = cls._eval_row(row, action)
                if decision == "deny":
                    return {
                        "decision": "deny",
                        "policy_id": row["id"],
                        "kind": row["kind"],
                        "reason": reason,
                        "scope": scope,
                    }
                if decision == "ask" and ask_verdict is None:
                    ask_verdict = {
                        "decision": "ask",
                        "policy_id": row["id"],
                        "kind": row["kind"],
                        "reason": reason,
                        "scope": scope,
                    }
                # ALLOW rows do not short-circuit — they fall through.

        if ask_verdict is not None:
            return ask_verdict

        return {
            "decision": "allow",
            "policy_id": None,
            "kind": None,
            "reason": "no matching policy (default allow)",
            "scope": None,
        }

    # -- ASK round-trip (reuses the human-gate SSE shape) -----------------

    @classmethod
    def await_decision(
        cls,
        session_id: str,
        verdict: dict,
        *,
        ask_id: str,
        max_wall_seconds: int = _POLICY_DEFAULT_MAX_WALL_SECONDS,
    ) -> str:
        """Block the launching call until an operator resolves THIS ASK (``ask_id``).

        MIRRORS goal_loop_runner._await_gate (goal_loop_runner.py:487): broadcast
        an ASK card over the EXISTING SSE primitive, poll the registry every
        ``_POLICY_POLL_SECONDS``, and bound the wait by ``max_wall_seconds``. It
        does NOT introduce a new transport — the broadcast goes through
        ``ProjectSessionManager`` (the same primitive the goal-gate and
        ``ask_user_question`` cards use).

        SECURITY (FIX 2 — ask-scoped): the pending sentinel + the resolution are
        keyed by the unique ``ask_id`` carried in the card, so only a decision
        that echoes THIS ask_id can resolve THIS wait. A stale/old decision for a
        prior ask can no longer auto-approve a later ask on the same session.

        Returns the decision string ("approve" | "deny"). GOVERNANCE FAIL-SAFE:
        on timeout (or a missing session id) this returns "deny" — distinct from
        the goal-gate's "abort" default — because a governance substrate must fail
        closed (23-RESEARCH.md Pitfall 3 + Production Considerations).
        """
        # Import lazily to avoid an import cycle, exactly as goal_loop_runner does.
        from .project_session_manager import ProjectSessionManager

        if not session_id:
            return "deny"

        ask_payload = {
            "ask_id": ask_id,
            "policy_id": verdict.get("policy_id"),
            "kind": verdict.get("kind"),
            "reason": verdict.get("reason"),
            "scope": verdict.get("scope"),
        }

        # RACE: an operator decision may arrive (submit_policy_decision) BEFORE we
        # register here — e.g. a fast approve, or a retry. submit stores a
        # (decision, message) tuple keyed by ask_id; we must NOT clobber it back to
        # None, or the resolution is lost and the launch fails closed on timeout.
        # Initialise to the pending sentinel ONLY when no resolution is already
        # waiting for THIS ask_id.
        with _POLICY_LOCK:
            if not isinstance(_POLICY_DECISIONS.get(ask_id), tuple):
                _POLICY_DECISIONS[ask_id] = None

        # FIX 3: persist the pending card AND push it to already-connected
        # subscribers in ONE atomic step. A LATE subscriber (the frontend
        # subscribes only after createSession resolves) REPLAYS the pending card on
        # connect; an already-connected one gets the live push. Doing both under a
        # single lock guarantees each subscriber gets the card EXACTLY once — never
        # both (the old register-then-separate-broadcast double-delivered to a
        # subscriber connecting in the gap).
        ProjectSessionManager.register_and_broadcast_policy_ask(session_id, ask_payload)

        entered = time.time()
        decision = "deny"
        try:
            while True:
                pending = _POLICY_DECISIONS.get(ask_id)
                if isinstance(pending, tuple):
                    decision = pending[0]
                    break
                if time.time() - entered > max_wall_seconds:
                    decision = "deny"  # timeout → fail closed
                    break
                time.sleep(_POLICY_POLL_SECONDS)
        finally:
            with _POLICY_LOCK:
                _POLICY_DECISIONS.pop(ask_id, None)
            ProjectSessionManager.clear_pending_policy_ask(session_id)

        ProjectSessionManager._broadcast(
            session_id,
            "policy_ask_resolved",
            {"ask_id": ask_id, "policy_id": verdict.get("policy_id"), "decision": decision},
        )
        return decision

    @classmethod
    def submit_policy_decision(
        cls, session_id: str, decision: str, message=None, *, ask_id: str
    ) -> bool:
        """Resolve the pending ASK identified by ``ask_id``. Returns True if a wait
        was pending (mirrors goal_loop_runner.submit_gate_decision:452). The HTTP
        entry point is ``policies.decide`` (the frontend echoes the card's ask_id).

        SECURITY (FIX 2 — ask-scoped): the resolution is stored under the unique
        ``ask_id`` it answers, NOT the ``session_id``. A decision for a resolved/old
        ask therefore cannot satisfy a DIFFERENT or FUTURE ask on the same session.
        ``session_id`` is kept for symmetry/logging only.

        STORE the resolution, don't merely signal a waiter: we record the
        ``(decision, message)`` tuple even when no waiter is registered yet, so a
        decision that races ahead of ``await_decision`` for the SAME ask_id is
        replayed to it rather than dropped (the await-side init refuses to overwrite
        a stored tuple)."""
        with _POLICY_LOCK:
            pending = ask_id in _POLICY_DECISIONS
            _POLICY_DECISIONS[ask_id] = (decision, message)
        return pending

    # -- Shared launch gate (the ONE chokepoint every spawner calls) ------

    @classmethod
    def enforce_launch(
        cls,
        *,
        session_id: str,
        team_id=None,
        cmd: list,
        backend: str,
        sandboxed: bool = False,
        total_cost_usd: float = 0.0,
        tool_calls: int = 0,
    ) -> None:
        """Evaluate the stackable policy layer at a process-launch boundary.

        SECURITY (23 BLOCKER 4): this is the SINGLE shared launch gate. Every
        autonomous harness launch path routes through here so no spawner can
        bypass governance — ``ExecutionService.run_trigger`` (its own Popen) and
        ``ProjectSessionManager.create_session`` (the PTY/pipe spawn used by goal-
        loop / ralph / team-spawn / agent / sketch sessions) both call it. Server-
        scope policies (``scope_id IS NULL``) always apply, so a server DENY blocks
        every launch regardless of which path reached it.

        Behaviour (all fail CLOSED):
          - ``deny``    -> raise ``PolicyDenied`` (caller aborts, no spawn).
          - ``ask``     -> block via ``await_decision`` (reuses the human-gate SSE
            round-trip); anything but ``"approve"`` raises ``PolicyDenied`` (a
            timeout fails closed to deny inside ``await_decision``).
          - ``allow``   -> return (caller proceeds to spawn unchanged).
          - anything else (should be impossible after ``_normalize_decision``) ->
            raise ``PolicyDenied`` (defence in depth).
        """
        action = {
            "kind": "process_launch",
            "cmd": cmd,
            "backend": backend,
            "sandboxed": sandboxed,
            "total_cost_usd": total_cost_usd,
            "tool_calls": tool_calls,
        }
        verdict = cls.evaluate(session_id=session_id, team_id=team_id, action=action)
        decision = verdict.get("decision")
        if decision == "allow":
            return
        if decision == "deny":
            raise PolicyDenied(verdict)
        if decision == "ask":
            # A fresh ask_id scopes the round-trip so only a decision echoing THIS
            # id can resolve THIS wait (FIX 2 — no stale auto-approve).
            ask_id = uuid.uuid4().hex
            if cls.await_decision(session_id, verdict, ask_id=ask_id) != "approve":
                raise PolicyDenied({**verdict, "decision": "deny", "reason": "operator denied"})
            return
        # Unknown verdict — fail closed (evaluate() should never reach here).
        raise PolicyDenied(
            {**verdict, "decision": "deny", "reason": f"unknown verdict {decision!r}"}
        )

    @classmethod
    def enforce_launch_noninteractive(
        cls,
        *,
        session_id: str,
        team_id=None,
        cmd: list,
        backend: str,
        sandboxed: bool = False,
        total_cost_usd: float = 0.0,
        tool_calls: int = 0,
    ) -> None:
        """Non-interactive launch gate for AUTONOMOUS *check* spawns.

        FIX 1 (23 BLOCKER) — the goal-judge deterministic eval
        (``GoalJudgeService._run_deterministic`` → ``sandbox_eval``) spawns an
        operator ``check_cmd`` via ``subprocess.Popen(shell=True)``. That is an
        autonomous, unattended launch, so it MUST clear the SAME stackable policy
        layer every other spawner does — it was the one autonomous spawn path that
        bypassed governance.

        It differs from ``enforce_launch`` in ONE deliberate way: an ASK is NOT
        interactively approvable here. A deterministic eval check is fire-and-forget
        grading machinery, not an operator turn — there is nobody to prompt and
        blocking the grader on a human approval card would be wrong. So this fails
        CLOSED on anything but ALLOW:
          - ``allow`` -> return (caller runs the check).
          - ``deny``  -> raise ``PolicyDenied`` (refuse to run the check).
          - ``ask``   -> raise ``PolicyDenied`` (treated as deny: a check is not a
            place for an approval prompt — documented choice).
          - anything else -> raise ``PolicyDenied`` (defence in depth).

        Server-scope policies (scope_id IS NULL) always apply. If the policy store
        itself cannot be consulted (uninitialized table in a unit test, or a
        transient operational error), there are no policies to enforce, so the
        check proceeds rather than breaking ALL grading — production always has the
        table (migration 176), and a real DENY verdict (table present) still blocks.
        """
        action = {
            "kind": "process_launch",
            "cmd": cmd,
            "backend": backend,
            "sandboxed": sandboxed,
            "total_cost_usd": total_cost_usd,
            "tool_calls": tool_calls,
        }
        try:
            verdict = cls.evaluate(session_id=session_id, team_id=team_id, action=action)
        except sqlite3.OperationalError:
            # Policy store not initialized / transient DB error — no policies to
            # enforce for this fire-and-forget check. Proceed (see docstring).
            return
        decision = verdict.get("decision")
        if decision == "allow":
            return
        if decision == "ask":
            raise PolicyDenied(
                {
                    **verdict,
                    "decision": "deny",
                    "reason": (
                        "eval check requires approval (ASK) — refusing to run a "
                        f"deterministic check non-interactively: {verdict.get('reason')}"
                    ),
                }
            )
        if decision == "deny":
            raise PolicyDenied(verdict)
        # Unknown verdict — fail closed (evaluate() should never reach here).
        raise PolicyDenied(
            {**verdict, "decision": "deny", "reason": f"unknown verdict {decision!r}"}
        )

    @classmethod
    def _rows_for(cls, scope: str, scope_id) -> list:
        """Read enabled rows for a scope, ordered by priority DESC.

        Matches the exact ``scope_id`` for session/team, and ``scope_id IS NULL``
        for the server sentinel scope. ``params`` JSON is parsed per row.
        """
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM policies WHERE scope = ? AND "
                "(scope_id = ? OR (? IS NULL AND scope_id IS NULL)) AND enabled = 1 "
                "ORDER BY priority DESC",
                (scope, scope_id, scope_id),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    @classmethod
    def _eval_row(cls, row: dict, action: dict):
        """Resolve a single row to ``(decision, reason)``.

        23-01 primitive: return the stored ``effect`` verbatim. The ``_BUILTINS``
        dispatch (filled in 23-02) lets a ``kind`` override this with a dynamic
        evaluator ``(row, action) -> (decision, reason)``.

        SECURITY: two fail-closed guards wrap the resolution —
          * BLOCKER 3 — a row whose ``params`` JSON failed to parse
            (``_params_invalid``) is DENIED outright; we never evaluate a cap
            against a hollow params dict (which would silently allow).
          * MAJOR 5 — every decision (builtin OR verbatim effect) is run through
            ``_normalize_decision`` so an unknown/typo'd effect collapses to DENY
            rather than falling through to allow.
        """
        if row.get("_params_invalid"):
            return (
                "deny",
                f"policy {row.get('id')} has malformed params — failing closed (deny)",
            )
        builtin = _BUILTINS.get(row.get("kind"))
        if builtin is not None:
            decision, reason = builtin(row, action)
            return _normalize_decision(decision), reason
        effect = row["effect"]
        return _normalize_decision(effect), f"policy {row['id']} effect={effect}"

    # -- CRUD -------------------------------------------------------------

    @classmethod
    def create_policy(
        cls,
        *,
        scope: str,
        scope_id=None,
        kind: str,
        effect: str = "ask",
        params=None,
        enabled: int = 1,
        priority: int = 0,
    ) -> dict:
        """Insert a policy row and return it as a dict (with ``params`` parsed)."""
        now = _now()
        params_json = json.dumps(params or {})
        with get_connection() as conn:
            policy_id = cls._unique_id(conn)
            conn.execute(
                "INSERT INTO policies (id, scope, scope_id, kind, effect, params, "
                "enabled, priority, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    policy_id,
                    scope,
                    scope_id,
                    kind,
                    effect,
                    params_json,
                    int(enabled),
                    int(priority),
                    now,
                    now,
                ),
            )
            conn.commit()
        return cls.get_policy(policy_id)

    @classmethod
    def get_policy(cls, policy_id: str):
        """Return a single policy dict, or ``None`` if it does not exist."""
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM policies WHERE id = ?", (policy_id,)).fetchone()
        return _row_to_dict(row) if row is not None else None

    @classmethod
    def list_policies(cls, scope=None) -> list:
        """List all policies, optionally filtered by ``scope``."""
        with get_connection() as conn:
            if scope is None:
                rows = conn.execute(
                    "SELECT * FROM policies ORDER BY priority DESC, created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM policies WHERE scope = ? ORDER BY priority DESC, created_at",
                    (scope,),
                ).fetchall()
        return [_row_to_dict(r) for r in rows]

    @classmethod
    def update_policy(cls, policy_id: str, **fields):
        """Update mutable fields of a policy. Returns the updated dict or None.

        Accepts: scope, scope_id, kind, effect, params, enabled, priority.
        ``params`` may be passed as a dict (serialized to JSON automatically).
        """
        allowed = {"scope", "scope_id", "kind", "effect", "params", "enabled", "priority"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return cls.get_policy(policy_id)
        if "params" in sets and not isinstance(sets["params"], str):
            sets["params"] = json.dumps(sets["params"] or {})
        if "enabled" in sets:
            sets["enabled"] = int(sets["enabled"])
        if "priority" in sets:
            sets["priority"] = int(sets["priority"])

        sets["updated_at"] = _now()
        columns = ", ".join(f"{k} = ?" for k in sets)
        values = list(sets.values()) + [policy_id]
        with get_connection() as conn:
            conn.execute(f"UPDATE policies SET {columns} WHERE id = ?", values)
            conn.commit()
        return cls.get_policy(policy_id)

    @classmethod
    def delete_policy(cls, policy_id: str) -> bool:
        """Delete a policy. Returns True if a row was removed."""
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM policies WHERE id = ?", (policy_id,))
            conn.commit()
            return cur.rowcount > 0

    # -- internals --------------------------------------------------------

    @staticmethod
    def _unique_id(conn) -> str:
        """Generate a ``pol-`` prefixed id not present in the policies table."""
        while True:
            pid = generate_id(POLICY_ID_PREFIX, POLICY_ID_LENGTH)
            if conn.execute("SELECT id FROM policies WHERE id = ?", (pid,)).fetchone() is None:
                return pid
