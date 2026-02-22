"""Tests for rotation dashboard API endpoints (/admin/rotation/*)."""

from app.db.connection import get_connection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_rotation_event(execution_id, from_account_id=None, to_account_id=None, reason=None):
    """Insert a rotation event directly, bypassing FK enforcement for test isolation."""
    import random
    import string

    event_id = "rev-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    with get_connection() as conn:
        # Temporarily disable FK enforcement for test data insertion
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO rotation_events (id, execution_id, from_account_id, to_account_id, reason, urgency)
            VALUES (?, ?, ?, ?, ?, 'normal')
            """,
            (event_id, execution_id, from_account_id, to_account_id, reason),
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    return event_id


def _insert_backend_account(account_id, account_name, backend_id="be-test"):
    """Insert a backend_accounts row directly for test JOINs."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO backend_accounts (id, backend_id, account_name, email)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, backend_id, account_name, f"{account_name}@test.com"),
        )
        conn.commit()


def _insert_ai_backend(backend_id="be-test", backend_type="claude"):
    """Insert a minimal ai_backends row (FK parent for backend_accounts)."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO ai_backends (id, name, type)
            VALUES (?, ?, ?)
            """,
            (backend_id, f"Test {backend_type}", backend_type),
        )
        conn.commit()


# ===========================================================================
# GET /admin/rotation/status
# ===========================================================================


class TestGetRotationStatus:
    """Tests for GET /admin/rotation/status."""

    def test_get_rotation_status_empty(self, client, isolated_db):
        """No active executions — returns empty sessions array and evaluator status."""
        resp = client.get("/admin/rotation/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sessions" in data
        assert "evaluator" in data
        assert data["sessions"] == []
        assert "job_id" in data["evaluator"]
        assert "evaluation_interval_seconds" in data["evaluator"]
        assert "hysteresis_threshold" in data["evaluator"]


# ===========================================================================
# GET /admin/rotation/history
# ===========================================================================


class TestGetRotationHistory:
    """Tests for GET /admin/rotation/history."""

    def test_get_rotation_history_empty(self, client, isolated_db):
        """No events — returns empty events array."""
        resp = client.get("/admin/rotation/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "events" in data
        assert data["events"] == []

    def test_get_rotation_history_with_events(self, client, isolated_db):
        """Insert events with matching backend accounts, verify enriched names."""
        _insert_ai_backend("be-test", "claude")
        _insert_backend_account(100, "Account Alpha")
        _insert_backend_account(200, "Account Beta")

        _insert_rotation_event(
            "exec-001", from_account_id=100, to_account_id=200, reason="high_util"
        )
        _insert_rotation_event(
            "exec-002", from_account_id=200, to_account_id=100, reason="cooldown"
        )
        _insert_rotation_event("exec-003", from_account_id=100, to_account_id=200, reason="eta_low")

        resp = client.get("/admin/rotation/history")
        assert resp.status_code == 200
        data = resp.get_json()
        events = data["events"]
        assert len(events) == 3

        # All events should have enriched account name fields
        for event in events:
            assert "from_account_name" in event
            assert "to_account_name" in event
            assert event["from_account_name"] in ("Account Alpha", "Account Beta")
            assert event["to_account_name"] in ("Account Alpha", "Account Beta")

    def test_get_rotation_history_limit(self, client, isolated_db):
        """Insert 5 events, request with limit=2, verify only 2 returned."""
        for i in range(5):
            _insert_rotation_event(f"exec-lim-{i}", reason=f"reason-{i}")

        resp = client.get("/admin/rotation/history?limit=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["events"]) == 2

    def test_get_rotation_history_by_execution(self, client, isolated_db):
        """Filter by execution_id returns only matching events."""
        _insert_rotation_event("exec-A", reason="reason-a")
        _insert_rotation_event("exec-A", reason="reason-a2")
        _insert_rotation_event("exec-B", reason="reason-b")

        resp = client.get("/admin/rotation/history?execution_id=exec-A")
        assert resp.status_code == 200
        data = resp.get_json()
        events = data["events"]
        assert len(events) == 2
        for event in events:
            assert event["execution_id"] == "exec-A"

    def test_get_rotation_history_deleted_account(self, client, isolated_db):
        """Account ID with no matching backend_accounts row shows 'Deleted Account'."""
        # Insert event with account IDs 9999 and 8888 — no matching rows
        _insert_rotation_event(
            "exec-del", from_account_id=9999, to_account_id=8888, reason="test_deleted"
        )

        resp = client.get("/admin/rotation/history")
        assert resp.status_code == 200
        data = resp.get_json()
        events = data["events"]
        assert len(events) == 1
        assert events[0]["from_account_name"] == "Deleted Account"
        assert events[0]["to_account_name"] == "Deleted Account"
