"""Pending permission-request registry (v0.7.69).

The Agented permission hook (``backend/scripts/agented_permission_hook.py``)
runs inside the claude subprocess on each ``PreToolUse``. It POSTs a
request to the Litestar backend and blocks waiting for the user's
Approve/Deny click in the web chat panel.

This module owns the wait/notify state. Each pending request is keyed
by a UUID and parked on a ``threading.Event``. The endpoint:

* ``POST /sessions/{sid}/permission-request`` (hook → backend)
  registers the request, broadcasts an SSE ``permission_request``
  event to the panel, and ``event.wait(timeout)`` until the user
  decides or the timeout fires.

* ``POST /sessions/{sid}/permission-decision`` (panel → backend)
  resolves the request — stores the decision and sets the event,
  unblocking the hook's HTTP response.

If the user never responds, the wait times out and the registry
returns ``None`` to the hook, which then falls back to claude's
default permission flow (``ask``) — never auto-allow, never
auto-deny on the absence of a click.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

_DEFAULT_TIMEOUT_SEC = 300  # 5 minutes


@dataclass
class _PendingRequest:
    request_id: str
    session_id: str
    tool_name: str
    tool_input: dict
    event: threading.Event = field(default_factory=threading.Event)
    decision: Optional[str] = None  # "allow" | "deny" | None (timeout)


class PermissionPromptRegistry:
    """Class-level singleton matching ``ProjectSessionManager`` style."""

    _pending: dict[str, _PendingRequest] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, session_id: str, tool_name: str, tool_input: dict) -> _PendingRequest:
        """Create a new pending request and return its handle.

        Caller (the hook endpoint) then ``wait()``s on the event and
        the SSE broadcaster reads ``request_id`` to push to the panel.
        """
        rid = f"perm-{uuid.uuid4().hex[:12]}"
        req = _PendingRequest(
            request_id=rid,
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )
        with cls._lock:
            cls._pending[rid] = req
        return req

    @classmethod
    def wait_for_decision(
        cls,
        request_id: str,
        timeout: float = _DEFAULT_TIMEOUT_SEC,
    ) -> Optional[str]:
        """Block until the user resolves the request or ``timeout``.

        Returns the decision string on success, ``None`` on timeout
        or if the request was never registered.
        """
        with cls._lock:
            req = cls._pending.get(request_id)
        if req is None:
            return None
        signaled = req.event.wait(timeout=timeout)
        with cls._lock:
            decision = req.decision if signaled else None
            cls._pending.pop(request_id, None)
        return decision

    @classmethod
    def resolve(cls, request_id: str, decision: str) -> bool:
        """Store the user's decision and unblock the waiting hook.

        Returns False if the request_id isn't known (already resolved
        or timed out).
        """
        if decision not in ("allow", "deny"):
            return False
        with cls._lock:
            req = cls._pending.get(request_id)
            if req is None or req.event.is_set():
                return False
            req.decision = decision
            req.event.set()
            return True

    @classmethod
    def cancel_session(cls, session_id: str) -> int:
        """Drop any pending requests for a session that's being torn
        down. Each waiting hook gets a None decision (treated as ask)
        and the registry is cleared. Returns the number cancelled."""
        cancelled = 0
        with cls._lock:
            for rid, req in list(cls._pending.items()):
                if req.session_id == session_id:
                    req.event.set()  # unblock waiters
                    cls._pending.pop(rid, None)
                    cancelled += 1
        return cancelled
