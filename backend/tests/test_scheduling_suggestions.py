"""Tests for scheduling suggestion service and API endpoint."""

from datetime import datetime, timedelta, timezone

from app.db.connection import get_connection


def _ensure_trigger(conn, trigger_id):
    """Create a trigger record if it doesn't exist."""
    conn.execute(
        """
        INSERT OR IGNORE INTO triggers (id, name, prompt_template, backend_type, trigger_source)
        VALUES (?, ?, 'test prompt', 'claude', 'webhook')
        """,
        (trigger_id, f"Test Trigger {trigger_id}"),
    )


def _insert_execution(conn, trigger_id, started_at, status="success", duration_minutes=5):
    """Helper to insert an execution log entry at a specific time."""
    finished_at = (
        (started_at + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if status == "success"
        else None
    )
    started_str = started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    import random
    import string

    exec_id = "exec-" + "".join(random.choices(string.ascii_lowercase, k=6))
    conn.execute(
        """
        INSERT INTO execution_logs
            (execution_id, trigger_id, trigger_type, backend_type, status, started_at, finished_at)
        VALUES (?, ?, 'webhook', 'claude', ?, ?, ?)
        """,
        (exec_id, trigger_id, status, started_str, finished_at),
    )
    return exec_id


class TestSchedulingSuggestionsWithData:
    """Test suggestions with sufficient data."""

    def test_scheduling_suggestions_with_data(self, client, isolated_db):
        """Insert 20+ executions across different hours with varying success rates.
        Hours 9-11 have 90% success, hours 2-4 have 50% success.
        Top suggestion hours should be the high-success ones."""
        with get_connection() as conn:
            _ensure_trigger(conn, "trig-test1")
            base = datetime.now(timezone.utc) - timedelta(days=10)

            # Hours 9, 10, 11 - high success rate (90%)
            for hour in [9, 10, 11]:
                for i in range(10):
                    dt = base.replace(hour=hour, minute=i * 5)
                    status = "success" if i < 9 else "failed"  # 9/10 = 90%
                    _insert_execution(conn, "trig-test1", dt, status=status, duration_minutes=3)

            # Hours 2, 3, 4 - low success rate (50%)
            for hour in [2, 3, 4]:
                for i in range(10):
                    dt = base.replace(hour=hour, minute=i * 5)
                    status = "success" if i < 5 else "failed"  # 5/10 = 50%
                    _insert_execution(conn, "trig-test1", dt, status=status, duration_minutes=8)

            conn.commit()

        resp = client.get("/admin/analytics/scheduling-suggestions")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_executions_analyzed"] == 60
        assert data["message"] is None

        # Get hour suggestions
        hour_suggestions = [s for s in data["suggestions"] if s["type"] == "hour"]
        assert len(hour_suggestions) == 3

        # Top 3 hours should be from 09, 10, 11 (highest success rate)
        top_hours = {s["value"] for s in hour_suggestions}
        assert top_hours == {"09:00", "10:00", "11:00"}

        # All should have 90% success rate
        for s in hour_suggestions:
            assert s["success_rate"] == 90.0

    def test_scheduling_suggestions_insufficient_data(self, client, isolated_db):
        """With only 3 executions, should return empty suggestions with message."""
        with get_connection() as conn:
            _ensure_trigger(conn, "trig-test2")
            base = datetime.now(timezone.utc) - timedelta(days=5)
            for i in range(3):
                dt = base.replace(hour=10, minute=i * 10)
                _insert_execution(conn, "trig-test2", dt, status="success")
            conn.commit()

        resp = client.get("/admin/analytics/scheduling-suggestions")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["suggestions"] == []
        assert data["total_executions_analyzed"] == 3
        assert "Not enough" in data["message"]
        assert "10" in data["message"]

    def test_scheduling_suggestions_per_trigger(self, client, isolated_db):
        """Filter suggestions by trigger_id, seeing only that trigger's patterns."""
        with get_connection() as conn:
            _ensure_trigger(conn, "trig-aaa")
            _ensure_trigger(conn, "trig-bbb")
            base = datetime.now(timezone.utc) - timedelta(days=10)

            # Trigger A: runs at hour 14 with high success
            for i in range(15):
                dt = base.replace(hour=14, minute=i * 3)
                _insert_execution(conn, "trig-aaa", dt, status="success", duration_minutes=2)

            # Trigger B: runs at hour 3 with high success
            for i in range(15):
                dt = base.replace(hour=3, minute=i * 3)
                _insert_execution(conn, "trig-bbb", dt, status="success", duration_minutes=2)

            conn.commit()

        # Query for trigger A only
        resp = client.get("/admin/analytics/scheduling-suggestions?trigger_id=trig-aaa")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_executions_analyzed"] == 15
        hour_suggestions = [s for s in data["suggestions"] if s["type"] == "hour"]
        assert len(hour_suggestions) >= 1
        # The top hour should be 14:00 (trigger A's time)
        assert hour_suggestions[0]["value"] == "14:00"
