"""Structured audit logging for execution events.

Produces JSON-formatted log records on the ``agented.audit`` logger so they can
be captured by any standard Python log handler (file, syslog, cloud sink, etc.)
without requiring a dedicated database table.

Each record shape:
    {
        "ts":          "<ISO-8601 UTC timestamp>",
        "action":      "<verb>",          # e.g. "execution.start"
        "entity_type": "<type>",          # e.g. "trigger", "workflow"
        "entity_id":   "<id>",
        "outcome":     "<result>",        # "started" | "success" | "failed" | ...
        "details":     { ... }            # optional structured context
    }

Field-level change records include a ``changes`` key in ``details``:
    {
        ...
        "details": {
            "changes": {
                "<field>": {"old": <old_value>, "new": <new_value>}
            }
        }
    }
"""

import collections
import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

audit_logger = logging.getLogger("agented.audit")

# In-memory ring buffer for recent audit events (visible via /admin/audit-events endpoint)
_RECENT_EVENTS_MAX = 500
_recent_events: collections.deque = collections.deque(maxlen=_RECENT_EVENTS_MAX)

# Fields that should never appear in audit diffs (secrets, large blobs)
_REDACTED_FIELDS: frozenset = frozenset(
    {"webhook_secret", "api_key", "password", "token", "prompt_template"}
)


class AuditLogService:
    """Emit structured JSON audit events via the ``agented.audit`` logger.

    Events are written to both the in-memory ring buffer (for real-time SSE)
    and to SQLite (for persistent, queryable history).
    """

    @staticmethod
    def log(
        action: str,
        entity_type: str,
        entity_id: str,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> None:
        """Emit a structured audit event.

        Args:
            action:      Short verb describing the operation, e.g. "execution.start".
            entity_type: Domain object type, e.g. "trigger", "workflow".
            entity_id:   Primary identifier of the entity.
            outcome:     Result of the action, e.g. "started", "success", "failed".
            details:     Optional dict of additional structured context.
            actor:       Who performed the action (default "system").
        """
        event: Dict[str, Any] = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "outcome": outcome,
            "actor": actor,
        }
        if details:
            event["details"] = details

        audit_logger.info(json.dumps(event))
        _recent_events.append(event)

        # Persist to SQLite (best-effort, never block caller)
        try:
            from ..db.audit_events import add_audit_event

            add_audit_event(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                outcome=outcome,
                actor=actor,
                details=details,
            )
        except Exception as exc:
            audit_logger.debug("Failed to persist audit event to SQLite: %s", exc)

    @staticmethod
    def log_field_changes(
        action: str,
        entity_type: str,
        entity_id: str,
        old_entity: Dict[str, Any],
        new_entity: Dict[str, Any],
        skip_fields: Optional[Sequence[str]] = None,
    ) -> None:
        """Emit an audit event that includes a field-level diff between old and new state.

        Only fields whose values actually changed are included. Fields listed in
        ``_REDACTED_FIELDS`` or ``skip_fields`` are omitted from the diff.

        Args:
            action:      Short verb, e.g. "trigger.update".
            entity_type: Domain object type, e.g. "trigger".
            entity_id:   Primary identifier of the entity.
            old_entity:  Dict representing the entity's state before the change.
            new_entity:  Dict representing the entity's state after the change.
            skip_fields: Additional field names to exclude from the diff.
        """
        excluded = _REDACTED_FIELDS | frozenset(skip_fields or [])
        changes: Dict[str, Dict[str, Any]] = {}

        all_keys = set(old_entity) | set(new_entity)
        for key in sorted(all_keys):
            if key in excluded:
                continue
            old_val = old_entity.get(key)
            new_val = new_entity.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        if not changes:
            return  # Nothing changed — skip emitting a noisy no-op event

        AuditLogService.log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome="updated",
            details={"changes": changes},
        )

    @staticmethod
    def query_events(
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query persistent audit events from SQLite with optional filters.

        Args:
            entity_type: Filter by entity type.
            entity_id: Filter by entity ID.
            actor: Filter by actor.
            start_date: ISO date for range start (inclusive).
            end_date: ISO date for range end (inclusive).
            limit: Max events to return.
            offset: Skip N events.

        Returns:
            List of audit event dicts, newest first.
        """
        from ..db.audit_events import query_audit_events

        return query_audit_events(
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_recent_events(limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent audit events from the in-memory buffer, newest first.

        Args:
            limit: Maximum number of events to return (capped at _RECENT_EVENTS_MAX).
        """
        limit = min(limit, _RECENT_EVENTS_MAX)
        events = list(_recent_events)
        events.reverse()
        return events[:limit]
