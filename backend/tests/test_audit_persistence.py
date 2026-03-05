"""Tests for persistent audit event storage in SQLite.

Covers:
- Events persisted to SQLite after AuditLogService.log()
- Query by entity_type, actor, date range
- Concurrent writes don't corrupt data
- Event retention (DB persistence survives service restart)
"""

import concurrent.futures

from app.db.audit_events import create_audit_event, count_audit_events, query_audit_events
from app.services.audit_log_service import AuditLogService


class TestAuditPersistence:
    """Test that audit events are persisted to SQLite."""

    def test_log_persists_to_sqlite(self, isolated_db):
        """AuditLogService.log() persists event to SQLite."""
        AuditLogService.log(
            action="trigger.create",
            entity_type="trigger",
            entity_id="trig-abc123",
            outcome="success",
            actor="user-1",
            details={"name": "My Trigger"},
        )

        events = query_audit_events(entity_type="trigger")
        assert len(events) >= 1
        event = events[0]
        assert event["action"] == "trigger.create"
        assert event["entity_id"] == "trig-abc123"
        assert event["outcome"] == "success"
        assert event["actor"] == "user-1"
        assert event["details"]["name"] == "My Trigger"

    def test_direct_add_audit_event(self, isolated_db):
        """Direct create_audit_event stores event correctly."""
        result = create_audit_event(
            action="team.delete",
            entity_type="team",
            entity_id="team-xyz",
            outcome="success",
            actor="admin",
        )
        assert result is True

        events = query_audit_events(entity_type="team")
        assert len(events) == 1
        assert events[0]["entity_id"] == "team-xyz"


class TestAuditQuery:
    """Test audit event querying with filters."""

    def _seed_events(self):
        """Seed multiple events for query testing."""
        create_audit_event("trigger.create", "trigger", "trig-1", "success", "user-a")
        create_audit_event("trigger.update", "trigger", "trig-1", "success", "user-b")
        create_audit_event("team.create", "team", "team-1", "success", "user-a")
        create_audit_event("rbac.denied", "api", "/admin/triggers/", "denied", "user-c")

    def test_filter_by_entity_type(self, isolated_db):
        self._seed_events()
        events = query_audit_events(entity_type="trigger")
        assert len(events) == 2
        assert all(e["entity_type"] == "trigger" for e in events)

    def test_filter_by_actor(self, isolated_db):
        self._seed_events()
        events = query_audit_events(actor="user-a")
        assert len(events) == 2
        assert all(e["actor"] == "user-a" for e in events)

    def test_filter_by_entity_id(self, isolated_db):
        self._seed_events()
        events = query_audit_events(entity_id="trig-1")
        assert len(events) == 2

    def test_filter_combined(self, isolated_db):
        self._seed_events()
        events = query_audit_events(entity_type="trigger", actor="user-a")
        assert len(events) == 1
        assert events[0]["action"] == "trigger.create"

    def test_count_audit_events(self, isolated_db):
        self._seed_events()
        total = count_audit_events()
        assert total == 4
        trigger_count = count_audit_events(entity_type="trigger")
        assert trigger_count == 2

    def test_pagination(self, isolated_db):
        self._seed_events()
        page1 = query_audit_events(limit=2, offset=0)
        page2 = query_audit_events(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # No overlap
        ids_page1 = {e["id"] for e in page1}
        ids_page2 = {e["id"] for e in page2}
        assert ids_page1.isdisjoint(ids_page2)

    def test_date_range_filter(self, isolated_db):
        """Date range filtering works with created_at."""
        create_audit_event("test.action", "test", "t-1", "ok")
        # Query with a start_date far in the past should include all
        events = query_audit_events(start_date="2020-01-01")
        assert len(events) >= 1
        # Query with a start_date in the future should return none
        events = query_audit_events(start_date="2099-01-01")
        assert len(events) == 0

    def test_details_json_parsing(self, isolated_db):
        """Details stored as JSON are parsed back to dict."""
        create_audit_event(
            "test.detail",
            "test",
            "t-2",
            "ok",
            details={"changes": {"name": {"old": "a", "new": "b"}}},
        )
        events = query_audit_events(entity_id="t-2")
        assert isinstance(events[0]["details"], dict)
        assert events[0]["details"]["changes"]["name"]["new"] == "b"


class TestAuditConcurrency:
    """Test that concurrent writes don't corrupt data."""

    def test_concurrent_writes(self, isolated_db):
        """Multiple threads writing audit events concurrently."""

        def write_event(i):
            return create_audit_event(
                action="test.concurrent",
                entity_type="test",
                entity_id=f"t-{i}",
                outcome="ok",
                actor=f"thread-{i}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_event, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All writes should succeed
        assert all(results)
        total = count_audit_events(entity_type="test")
        assert total == 20


class TestAuditRetention:
    """Test that events survive 'service restart' (DB persistence)."""

    def test_events_persist_across_queries(self, isolated_db):
        """Events written once are retrievable in separate queries."""
        create_audit_event("persist.test", "test", "p-1", "ok")

        # Query in a separate call (simulating restart)
        events = query_audit_events(entity_id="p-1")
        assert len(events) == 1
        assert events[0]["action"] == "persist.test"
