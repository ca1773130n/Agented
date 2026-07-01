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
