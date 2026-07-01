"""SessionSharingService — live-share attach + co-drive gate (Phase 25).

25-01 (live-share): ``can_attach`` resolves a scoped share token and confirms it
is bound to the session being attached, returning the scope (``read``|``chat``)
or ``None``. The read attach route joins the EXISTING
``ProjectSessionManager.subscribe`` fan-out — no new broadcast machinery.

25-02 (co-drive): ``co_drive`` requires a ``chat`` scope, routes the teammate's
message through the Phase-23 policy engine (``PolicyService``) BEFORE it reaches
``ProjectSessionManager.send_input``, and broadcasts an attribution event so the
operator's stream shows WHO drove. A DENY blocks the write (send_input is never
called); an ASK blocks (bounded) until the operator resolves it; ALLOW proceeds.

Co-drive respects the operator's per-project allowed-accounts structurally: the
teammate message executes against the operator's ALREADY-RUNNING session (which
was launched under the operator's allowed account) — the teammate never selects
a backend/account, so it cannot escape that constraint.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from ..db.session_shares import resolve_share_token

logger = logging.getLogger(__name__)


class CoDriveScopeError(Exception):
    """Raised when a non-``chat`` token is used on the co-drive write path."""


def _session_tool_call_count(session_id: str) -> int:
    """Best-effort per-session tool-call proxy (goal-loop iterations executed).

    The goal-loop's own cost gate uses its iteration count as the ``tool_calls``
    ctx (``goal_loop_runner``), so we mirror that: the number of recorded
    iterations for the session. 0 when the table is absent or the session has
    none — never raises.
    """
    if not session_id:
        return 0
    from ..db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM goal_loop_iterations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return 0
    return int(row["n"] if not isinstance(row, tuple) else row[0])


def _session_policy_context(session_id: str) -> dict:
    """Snapshot the co-driven session's REAL running totals for the policy gate.

    SECURITY (25 MAJOR — co-drive was toothless): the policy action ctx used to
    carry zeroed cost/tool/backend/sandbox, so ``cost_budget`` /
    ``max_tool_calls_per_session`` / ``enforce_sandbox`` builtins could never trip
    for a teammate's action. We now source the operator session's actual
    accumulated context so those caps apply to the co-driver too. Every lookup is
    defensive — a missing source degrades to a conservative default, never a
    500.
    """
    total_cost_usd = 0.0
    tool_calls = 0
    backend: Optional[str] = None

    try:
        from ..db.budgets import get_session_total_cost

        total_cost_usd = get_session_total_cost(session_id)
    except Exception:  # noqa: BLE001
        logger.debug("co_drive: session cost lookup failed", exc_info=True)

    try:
        from .project_session_manager import ProjectSessionManager

        si = ProjectSessionManager._sessions.get(session_id)
        if si is not None:
            backend = getattr(si, "backend", None)
    except Exception:  # noqa: BLE001
        logger.debug("co_drive: live-session backend lookup failed", exc_info=True)

    if not backend:
        try:
            from ..db.connection import get_connection

            with get_connection() as conn:
                row = conn.execute(
                    "SELECT backend FROM project_sessions WHERE id = ?", (session_id,)
                ).fetchone()
            if row is not None:
                backend = row["backend"] if not isinstance(row, tuple) else row[0]
        except Exception:  # noqa: BLE001
            logger.debug("co_drive: persisted backend lookup failed", exc_info=True)

    try:
        tool_calls = _session_tool_call_count(session_id)
    except Exception:  # noqa: BLE001
        logger.debug("co_drive: tool-call count lookup failed", exc_info=True)

    return {
        "total_cost_usd": total_cost_usd or 0.0,
        "tool_calls": tool_calls or 0,
        "backend": backend or "unknown",
        # send_input is not a launch kind so ``sandboxed`` is inert for this
        # verdict, but we pass the honest flag: co-drive never sandboxes the
        # operator's already-running session.
        "sandboxed": False,
    }


class SessionSharingService:
    """Classmethod service (no instance state) for shared-session attach + co-drive."""

    @classmethod
    def can_attach(cls, token: str, session_id: str) -> Optional[str]:
        """Resolve ``token`` and return its scope iff it is bound to ``session_id``.

        Returns ``None`` when the token is unknown / revoked / expired, or when it
        was minted for a DIFFERENT session (a token is scoped to exactly one
        session). Fail closed.
        """
        row = resolve_share_token(token)
        if not row:
            return None
        if row.get("session_id") != session_id:
            return None
        return row.get("scope")

    @classmethod
    def co_drive(
        cls,
        session_id: str,
        token: str,
        text: str,
        actor_user_id: str,
        *,
        team_id: Optional[str] = None,
        max_wall_seconds: int = 120,
    ) -> bool:
        """Execute a teammate's ``text`` against the operator's running session.

        SHARP EDGE (25-02): a teammate's action running on the operator's session
        MUST NOT exceed the operator's policy. The message is gated by the Phase-23
        policy engine (``PolicyService.evaluate`` keyed to the operator's SESSION
        scope, actor = the TEAMMATE) BEFORE it reaches stdin:

          * a ``read`` token is rejected before any policy/IO (``CoDriveScopeError``),
          * DENY  → raise ``PolicyDenied`` (``send_input`` is NEVER called),
          * ASK   → block via ``PolicyService.await_decision`` (BOUNDED by
            ``max_wall_seconds``); anything but ``approve`` → ``PolicyDenied``,
          * ALLOW → broadcast a ``co_drive`` attribution event, then
            ``send_input(session_id, text)`` and return its bool.

        The operator's OWN ``send_input`` path is untouched — co-drive wraps only
        the shared-token route. Co-drive respects the operator's per-project
        allowed-accounts structurally: the message executes against the operator's
        ALREADY-RUNNING session (launched under the operator's allowed account);
        the teammate never selects a backend/account, so cannot escape it.
        """
        # 1) Scope check — a read token physically cannot reach the write path.
        scope = cls.can_attach(token, session_id)
        if scope != "chat":
            raise CoDriveScopeError(
                "co-drive requires a 'chat'-scope share token bound to this session"
            )

        # 2) Route through the Phase-23 policy engine BEFORE any IO. Imported
        #    lazily to avoid an import cycle (policy_service imports the PSM).
        from .policy_service import PolicyDenied, PolicyService
        from .project_session_manager import ProjectSessionManager

        # A co-drive input is an action on the operator's session; the actor is the
        # TEAMMATE (not the operator), so governance applies to who is actually
        # driving. Keyed to the session scope; PolicyService walks session→team→server.
        action = {
            "kind": "session.send_input",
            "actor_user_id": actor_user_id,
            "session_id": session_id,
            "text_summary": (text or "")[:200],
            # 25 MAJOR fix — the co-driven session's REAL accumulated context, so
            # cost/tool-call/sandbox caps actually gate the teammate's action
            # instead of always seeing zeroed cost/tool_calls.
            **_session_policy_context(session_id),
        }
        verdict = PolicyService.evaluate(session_id=session_id, team_id=team_id, action=action)
        decision = verdict.get("decision")

        if decision == "deny":
            raise PolicyDenied(verdict)
        if decision == "ask":
            ask_id = uuid.uuid4().hex
            resolved = PolicyService.await_decision(
                session_id, verdict, ask_id=ask_id, max_wall_seconds=max_wall_seconds
            )
            if resolved != "approve":
                raise PolicyDenied(
                    {**verdict, "decision": "deny", "reason": "co-drive not approved"}
                )
        elif decision != "allow":
            # Defence in depth — evaluate() should only ever return allow/deny/ask.
            raise PolicyDenied(
                {**verdict, "decision": "deny", "reason": f"unknown verdict {decision!r}"}
            )

        # 3) ALLOW / approved-ASK → attribute + drive the operator's session.
        ProjectSessionManager._broadcast(
            session_id,
            "co_drive",
            {"actor_user_id": actor_user_id, "text": text},
        )
        return ProjectSessionManager.send_input(session_id, text)
