"""Execution-completion event channel — decouples execution from trigger.

Before this module, ``WorkflowExecutionService._run_workflow`` lazy-imported
``WorkflowTriggerService`` to call ``on_execution_complete``. That created a
bidirectional runtime dependency: trigger service also imports execution
service (lazy) to *start* workflows. Codex F7 flagged the cycle.

This module flips the dependency. ``WorkflowExecutionService`` dispatches a
completion event into this registry; ``WorkflowTriggerService.on_execution_complete``
is registered as a handler at startup (see ``app_litestar/lifecycle.py``).

The execution side never imports the trigger side. The trigger side still
imports the execution side (one-way), which is acceptable.

Public API:
    register_completion_handler(callback)  — wire a handler at startup.
    emit_execution_complete(...)           — call from execution-completion paths.
    clear_completion_handlers()            — test helper; never call from prod.

Handler signature:
    def handler(entity_type: str, entity_id: str, status: str,
                output: dict | None) -> None
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

CompletionCallback = Callable[[str, str, str, Optional[dict]], None]

_handlers: list[CompletionCallback] = []


def register_completion_handler(callback: CompletionCallback) -> None:
    """Register a handler fired on every execution completion event.

    Idempotent: registering the same callable twice keeps it once. Lifecycle
    startup may re-register on reload; tests may register handlers and then
    call ``clear_completion_handlers()``.
    """
    if callback in _handlers:
        return
    _handlers.append(callback)


def emit_execution_complete(
    entity_type: str,
    entity_id: str,
    status: str,
    output: Optional[dict],
) -> None:
    """Fire all registered handlers. Per-handler exceptions are swallowed +
    logged so one buggy handler can't block the completion of another or
    abort the calling execution path.
    """
    for handler in list(_handlers):
        try:
            handler(entity_type, entity_id, status, output)
        except Exception:
            logger.exception(
                "execution_events handler %r raised on %s/%s",
                handler,
                entity_type,
                entity_id,
            )


def clear_completion_handlers() -> None:
    """Test-only — wipe all registered handlers."""
    _handlers.clear()
