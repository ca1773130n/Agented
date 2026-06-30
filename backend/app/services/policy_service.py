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
from datetime import datetime, timezone

from ..database import get_connection
from ..db.ids import generate_id

logger = logging.getLogger(__name__)

POLICY_ID_PREFIX = "pol-"
POLICY_ID_LENGTH = 6


class PolicyDenied(Exception):
    """Raised by enforcement plans (23-03) when evaluate() returns a DENY verdict.

    Carries the offending verdict dict on ``.verdict`` for callers that want to
    surface the policy id / reason.
    """

    def __init__(self, verdict: dict):
        self.verdict = verdict
        reason = verdict.get("reason") or "policy denied"
        super().__init__(reason)


# Extension seam for 23-02: maps a policy ``kind`` to a builtin evaluator
# callable ``(row, action) -> (decision, reason)``. Empty in this plan — every
# row falls back to its stored ``effect`` (see ``_eval_row``).
_BUILTINS: dict = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict, parsing ``params`` JSON."""
    d = dict(row)
    raw = d.get("params")
    if isinstance(raw, str):
        try:
            d["params"] = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            d["params"] = {}
    elif raw is None:
        d["params"] = {}
    return d


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
        """
        builtin = _BUILTINS.get(row.get("kind"))
        if builtin is not None:
            return builtin(row, action)
        return row["effect"], f"policy {row['id']} effect={row['effect']}"

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
