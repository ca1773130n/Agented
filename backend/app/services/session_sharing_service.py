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
