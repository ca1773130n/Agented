"""Tests for AuditLogService."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.audit_log_service import (
    AuditLogService,
    _REDACTED_FIELDS,
    _recent_events,
)


@pytest.fixture(autouse=True)
def clear_recent_events():
    """Clear the in-memory ring buffer before and after each test."""
    _recent_events.clear()
    yield
    _recent_events.clear()


# ---------------------------------------------------------------------------
# log()
# ---------------------------------------------------------------------------


class TestLog:
    def test_creates_structured_event_with_all_fields(self):
        """log() produces an event dict with ts, action, entity_type, entity_id, outcome, actor."""
        AuditLogService.log(
            action="bot.create",
            entity_type="bot",
            entity_id="bot-abc123",
            outcome="success",
            details={"name": "My Bot"},
            actor="user-1",
        )

        assert len(_recent_events) == 1
        event = _recent_events[0]
        assert event["action"] == "bot.create"
        assert event["entity_type"] == "bot"
        assert event["entity_id"] == "bot-abc123"
        assert event["outcome"] == "success"
        assert event["actor"] == "user-1"
        assert event["details"] == {"name": "My Bot"}
        assert event["ts"].endswith("Z")

    def test_default_actor_is_system(self):
        """When no actor is provided, it defaults to 'system'."""
        AuditLogService.log(
            action="execution.start",
            entity_type="trigger",
            entity_id="trg-000001",
            outcome="started",
        )

        event = _recent_events[0]
        assert event["actor"] == "system"

    def test_details_omitted_when_none(self):
        """When details is None, the event dict should not contain a 'details' key."""
        AuditLogService.log(
            action="execution.start",
            entity_type="trigger",
            entity_id="trg-000001",
            outcome="started",
        )

        event = _recent_events[0]
        assert "details" not in event

    def test_appends_to_recent_events(self):
        """Each call to log() appends exactly one event to _recent_events."""
        for i in range(5):
            AuditLogService.log(
                action=f"action.{i}",
                entity_type="test",
                entity_id=f"id-{i}",
                outcome="ok",
            )

        assert len(_recent_events) == 5

    def test_emits_json_to_logger(self, caplog):
        """log() writes a JSON-serialised event to the agented.audit logger."""
        with caplog.at_level(logging.INFO, logger="agented.audit"):
            AuditLogService.log(
                action="bot.delete",
                entity_type="bot",
                entity_id="bot-xyz",
                outcome="success",
            )

        assert len(caplog.records) == 1
        payload = json.loads(caplog.records[0].message)
        assert payload["action"] == "bot.delete"

    def test_sqlite_persistence_failure_is_graceful(self, caplog):
        """If SQLite persistence raises, the event is still in _recent_events and no exception propagates."""
        with patch(
            "app.services.audit_log_service.create_audit_event",
            side_effect=RuntimeError("db locked"),
            create=True,
        ):
            # Patch the lazy import inside log()
            with patch(
                "app.db.audit_events.create_audit_event",
                side_effect=RuntimeError("db locked"),
            ):
                AuditLogService.log(
                    action="execution.start",
                    entity_type="trigger",
                    entity_id="trg-fail",
                    outcome="started",
                )

        # Event still buffered despite DB failure
        assert len(_recent_events) == 1
        assert _recent_events[0]["entity_id"] == "trg-fail"


# ---------------------------------------------------------------------------
# log_field_changes()
# ---------------------------------------------------------------------------


class TestLogFieldChanges:
    def test_includes_only_changed_fields(self):
        """Only fields whose values differ appear in the changes dict."""
        old = {"name": "Old Name", "status": "active", "description": "same"}
        new = {"name": "New Name", "status": "inactive", "description": "same"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-001",
            old_entity=old,
            new_entity=new,
        )

        assert len(_recent_events) == 1
        changes = _recent_events[0]["details"]["changes"]
        assert "name" in changes
        assert changes["name"] == {"old": "Old Name", "new": "New Name"}
        assert "status" in changes
        assert changes["status"] == {"old": "active", "new": "inactive"}
        assert "description" not in changes

    def test_skips_redacted_fields(self):
        """Fields in _REDACTED_FIELDS must never appear in the diff."""
        old = {"name": "Bot", "webhook_secret": "old-secret", "api_key": "old-key"}
        new = {"name": "Bot2", "webhook_secret": "new-secret", "api_key": "new-key"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-002",
            old_entity=old,
            new_entity=new,
        )

        changes = _recent_events[0]["details"]["changes"]
        for field in _REDACTED_FIELDS:
            assert field not in changes
        assert "name" in changes

    def test_skips_custom_skip_fields(self):
        """Additional skip_fields are also excluded from the diff."""
        old = {"name": "A", "internal_id": "x"}
        new = {"name": "B", "internal_id": "y"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-003",
            old_entity=old,
            new_entity=new,
            skip_fields=["internal_id"],
        )

        changes = _recent_events[0]["details"]["changes"]
        assert "internal_id" not in changes
        assert "name" in changes

    def test_no_event_when_nothing_changed(self):
        """If old and new are identical (ignoring redacted), no event is emitted."""
        entity = {"name": "Same", "status": "active"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-004",
            old_entity=entity,
            new_entity=dict(entity),  # identical copy
        )

        assert len(_recent_events) == 0

    def test_no_event_when_only_redacted_fields_changed(self):
        """If the only changes are in redacted fields, no event is emitted."""
        old = {"name": "Bot", "webhook_secret": "old", "token": "old-tok"}
        new = {"name": "Bot", "webhook_secret": "new", "token": "new-tok"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-005",
            old_entity=old,
            new_entity=new,
        )

        assert len(_recent_events) == 0

    def test_handles_added_and_removed_fields(self):
        """Fields present in only one dict should show None for the missing side."""
        old = {"name": "Bot"}
        new = {"name": "Bot", "description": "Added"}

        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-006",
            old_entity=old,
            new_entity=new,
        )

        changes = _recent_events[0]["details"]["changes"]
        assert changes["description"] == {"old": None, "new": "Added"}

    def test_outcome_is_updated(self):
        """log_field_changes() always sets outcome to 'updated'."""
        AuditLogService.log_field_changes(
            action="bot.update",
            entity_type="bot",
            entity_id="bot-007",
            old_entity={"name": "A"},
            new_entity={"name": "B"},
        )

        assert _recent_events[0]["outcome"] == "updated"


# ---------------------------------------------------------------------------
# get_recent_events()
# ---------------------------------------------------------------------------


class TestGetRecentEvents:
    def _populate(self, n: int):
        """Helper: insert n events with sequential action names."""
        for i in range(n):
            AuditLogService.log(
                action=f"action.{i}",
                entity_type="test",
                entity_id=f"id-{i}",
                outcome="ok",
            )

    def test_returns_reverse_chronological_order(self):
        """Newest event should be first in the returned list."""
        self._populate(3)

        events = AuditLogService.get_recent_events()
        assert events[0]["action"] == "action.2"
        assert events[1]["action"] == "action.1"
        assert events[2]["action"] == "action.0"

    def test_respects_limit(self):
        """Only `limit` events should be returned."""
        self._populate(10)

        events = AuditLogService.get_recent_events(limit=3)
        assert len(events) == 3
        # Should be the 3 most recent
        assert events[0]["action"] == "action.9"

    def test_returns_empty_list_when_no_events(self):
        """When no events have been logged, returns an empty list."""
        events = AuditLogService.get_recent_events()
        assert events == []

    def test_limit_capped_at_max(self):
        """Requesting more than _RECENT_EVENTS_MAX still works without error."""
        self._populate(5)

        events = AuditLogService.get_recent_events(limit=99999)
        assert len(events) == 5


# ---------------------------------------------------------------------------
# query_events()
# ---------------------------------------------------------------------------


class TestQueryEvents:
    def test_delegates_to_db_function(self, isolated_db):
        """query_events() calls the underlying DB query function with its arguments."""
        with patch("app.db.audit_events.query_audit_events", return_value=[]) as mock_query:
            result = AuditLogService.query_events(
                entity_type="bot",
                entity_id="bot-001",
                actor="system",
                start_date="2026-01-01",
                end_date="2026-12-31",
                limit=50,
                offset=10,
            )

            mock_query.assert_called_once_with(
                entity_type="bot",
                entity_id="bot-001",
                actor="system",
                start_date="2026-01-01",
                end_date="2026-12-31",
                limit=50,
                offset=10,
            )
            assert result == []
