"""Session-completion event channel.

Originally a workflow-only ``execution_events`` channel; now generalized
to all session producers (trigger executions, workflow nodes, super-agent
sessions, project sessions).

Public API:
    register_session_handler(callback)      — register at startup
    emit_session_complete(...)              — call from session-completion paths
    clear_session_handlers()                — test helper

Compat shims kept for any callers that haven't migrated yet:
    register_completion_handler  ← register_session_handler
    emit_execution_complete      ← emit_session_complete (entity_type ↦ session_kind,
                                                          entity_id ↦ session_id)

Handler signature:
    def handler(session_kind: str, session_id: str, project_id: Optional[str],
                status: str, output: dict | None) -> None
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# (session_kind, session_id, project_id, status, output) -> None
SessionCallback = Callable[
    [str, str, Optional[str], str, Optional[dict]],
    None,
]

_handlers: list[SessionCallback] = []


def register_session_handler(callback: SessionCallback) -> None:
    """Register a handler fired on every session-completion event.

    Idempotent: registering the same callable twice keeps it once.
    """
    if callback in _handlers:
        return
    _handlers.append(callback)


def emit_session_complete(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """Fire all registered handlers. Per-handler exceptions are swallowed +
    logged so one buggy handler can't block another or abort the calling
    session-completion path."""
    for handler in list(_handlers):
        try:
            handler(session_kind, session_id, project_id, status, output)
        except Exception:
            logger.exception(
                "session_events handler %r raised on %s/%s",
                handler,
                session_kind,
                session_id,
            )


def clear_session_handlers() -> None:
    """Test-only — wipe all registered handlers."""
    _handlers.clear()


# ---------------------------------------------------------------------------
# Compat shims for callers that haven't migrated to the session-scoped API
# ---------------------------------------------------------------------------

# entity_type ↦ session_kind translation. Workflow-side callers pass
# ``entity_type='workflow'``; we preserve that label.
_LEGACY_KIND_MAP = {
    "workflow": "workflow",
    "trigger": "trigger_execution",
}

CompletionCallback = Callable[[str, str, str, Optional[dict]], None]


def register_completion_handler(callback: CompletionCallback) -> None:
    """Legacy 4-arg handler signature: ``(entity_type, entity_id, status, output)``.

    Wrapped so it can subscribe to the new 5-arg session channel.
    """

    def _shim(session_kind, session_id, project_id, status, output):
        try:
            callback(session_kind, session_id, status, output)
        except Exception:
            # Keep the "execution_events handler" phrasing so legacy tests
            # asserting on this log message continue to pass.
            logger.exception(
                "execution_events handler %r raised on %s/%s",
                callback,
                session_kind,
                session_id,
            )

    _shim.__wrapped_target__ = callback  # type: ignore[attr-defined]
    if any(getattr(h, "__wrapped_target__", None) is callback for h in _handlers):
        return
    _handlers.append(_shim)


def emit_execution_complete(
    entity_type: str,
    entity_id: str,
    status: str,
    output: Optional[dict],
) -> None:
    """Legacy emitter. Maps ``entity_type`` to a ``session_kind`` and
    delegates to ``emit_session_complete``. ``project_id`` is unknown
    in the legacy contract — handlers either tolerate ``None`` or
    resolve the project themselves."""
    session_kind = _LEGACY_KIND_MAP.get(entity_type, entity_type)
    emit_session_complete(session_kind, entity_id, None, status, output)


def clear_completion_handlers() -> None:
    """Legacy test-only helper."""
    clear_session_handlers()
