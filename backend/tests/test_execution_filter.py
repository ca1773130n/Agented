"""Tests verifying execution filtering with composed filters.

Seeds 20 execution records with varying statuses, trigger_ids, dates, and output
text. Verifies:
- Filter by status alone returns only matching executions
- Filter by trigger_id alone returns only executions for that trigger
- Filter by date range returns only executions in range
- Filter by text search returns executions containing search term in output
- Composed filters use AND logic (intersection)
- Pagination composes with filters
"""

import pytest

from app import create_app
from app.db.connection import get_connection
from app.db.executions import count_filtered_executions, get_filtered_executions


@pytest.fixture
def client(isolated_db):
    """Create a Flask test client with isolated DB."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def seed_executions(isolated_db):
    """Seed 20 execution records with varying statuses, trigger_ids, dates, and output."""
    with get_connection() as conn:
        # Insert parent trigger rows first (FK constraint on execution_logs.trigger_id)
        for tid in ["trig-aaa", "trig-bbb", "trig-ccc"]:
            conn.execute(
                """INSERT INTO triggers (id, name, trigger_source, prompt_template)
                   VALUES (?, ?, 'webhook', 'test prompt')""",
                (tid, f"Test trigger {tid}"),
            )

        records = []
        statuses = ["completed", "completed", "failed", "running", "cancelled"]
        trigger_ids = ["trig-aaa", "trig-aaa", "trig-bbb", "trig-bbb", "trig-ccc"]

        for i in range(20):
            status = statuses[i % len(statuses)]
            trigger_id = trigger_ids[i % len(trigger_ids)]
            # Spread dates across March 2026
            day = (i % 5) + 1
            started_at = f"2026-03-{day:02d}T10:00:00"

            # Add "security" keyword to some executions for text search testing
            stdout_log = f"Execution {i} output"
            if i % 4 == 0:
                stdout_log += " security scan complete"

            stderr_log = f"stderr line {i}"

            execution_id = f"exec-test-{i:03d}"
            conn.execute(
                """INSERT INTO execution_logs
                   (execution_id, trigger_id, trigger_type, started_at,
                    status, stdout_log, stderr_log, prompt, backend_type, command)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    trigger_id,
                    "webhook",
                    started_at,
                    status,
                    stdout_log,
                    stderr_log,
                    f"prompt {i}",
                    "claude",
                    f"claude -p 'test {i}'",
                ),
            )
            records.append({
                "execution_id": execution_id,
                "trigger_id": trigger_id,
                "status": status,
                "started_at": started_at,
                "stdout_log": stdout_log,
            })

        conn.commit()

    return records


class TestFilterByStatus:
    """Test filtering by status alone."""

    def test_filter_completed(self, seed_executions):
        """status=completed returns only completed executions."""
        results = get_filtered_executions(status="completed")
        assert len(results) > 0
        for r in results:
            assert r["status"] == "completed"

    def test_filter_failed(self, seed_executions):
        """status=failed returns only failed executions."""
        results = get_filtered_executions(status="failed")
        assert len(results) > 0
        for r in results:
            assert r["status"] == "failed"

    def test_count_matches_results(self, seed_executions):
        """count_filtered_executions matches len of get_filtered_executions."""
        results = get_filtered_executions(status="completed")
        count = count_filtered_executions(status="completed")
        assert count == len(results)


class TestFilterByTriggerId:
    """Test filtering by trigger_id alone."""

    def test_filter_trigger_aaa(self, seed_executions):
        """trigger_id=trig-aaa returns only executions for that trigger."""
        results = get_filtered_executions(trigger_id="trig-aaa")
        assert len(results) > 0
        for r in results:
            assert r["trigger_id"] == "trig-aaa"

    def test_count_by_trigger(self, seed_executions):
        """Count by trigger_id matches result length."""
        results = get_filtered_executions(trigger_id="trig-bbb")
        count = count_filtered_executions(trigger_id="trig-bbb")
        assert count == len(results)


class TestFilterByDateRange:
    """Test filtering by date range."""

    def test_date_range(self, seed_executions):
        """date_from and date_to narrow results to the specified range."""
        results = get_filtered_executions(
            date_from="2026-03-01", date_to="2026-03-02T23:59:59"
        )
        assert len(results) > 0
        for r in results:
            assert r["started_at"] >= "2026-03-01"
            assert r["started_at"] <= "2026-03-02T23:59:59"


class TestFilterByTextSearch:
    """Test text search over execution output."""

    def test_search_security(self, seed_executions):
        """q=security returns executions containing 'security' in stdout_log."""
        results = get_filtered_executions(q="security")
        assert len(results) > 0
        for r in results:
            has_match = "security" in (r.get("stdout_log") or "").lower() or \
                        "security" in (r.get("stderr_log") or "").lower()
            assert has_match

    def test_search_no_match(self, seed_executions):
        """q with no matching text returns 0 results."""
        results = get_filtered_executions(q="xyznonexistent123")
        assert len(results) == 0


class TestComposedFilters:
    """Test that filters compose with AND logic."""

    def test_status_and_trigger_id(self, seed_executions):
        """status=completed AND trigger_id=trig-aaa returns intersection."""
        results = get_filtered_executions(status="completed", trigger_id="trig-aaa")
        for r in results:
            assert r["status"] == "completed"
            assert r["trigger_id"] == "trig-aaa"

        # Should be fewer than either filter alone
        only_status = get_filtered_executions(status="completed")
        only_trigger = get_filtered_executions(trigger_id="trig-aaa")
        assert len(results) <= len(only_status)
        assert len(results) <= len(only_trigger)

    def test_status_trigger_and_date(self, seed_executions):
        """Three-way AND: status + trigger_id + date range."""
        results = get_filtered_executions(
            status="completed", trigger_id="trig-aaa",
            date_from="2026-03-01", date_to="2026-03-01T23:59:59"
        )
        for r in results:
            assert r["status"] == "completed"
            assert r["trigger_id"] == "trig-aaa"
            assert r["started_at"] >= "2026-03-01"
            assert r["started_at"] <= "2026-03-01T23:59:59"


class TestPaginationWithFilters:
    """Test that pagination composes with filters."""

    def test_paginated_filter(self, seed_executions):
        """Pagination works correctly with status filter."""
        # Get all completed executions
        all_completed = get_filtered_executions(status="completed", limit=500)
        total = count_filtered_executions(status="completed")
        assert total == len(all_completed)

        if total >= 2:
            # Get first page
            page1 = get_filtered_executions(status="completed", limit=1, offset=0)
            assert len(page1) == 1
            assert page1[0]["status"] == "completed"

            # Get second page
            page2 = get_filtered_executions(status="completed", limit=1, offset=1)
            assert len(page2) == 1
            assert page2[0]["status"] == "completed"

            # Items should be different
            assert page1[0]["execution_id"] != page2[0]["execution_id"]


class TestExecutionFilterAPI:
    """Test the HTTP API with ExecutionFilterQuery parameters."""

    def test_api_filter_by_status(self, client, seed_executions):
        """GET /admin/executions?status=completed filters by status."""
        resp = client.get("/admin/executions?status=completed")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "executions" in data
        assert "total_count" in data
        for ex in data["executions"]:
            assert ex["status"] == "completed"

    def test_api_filter_by_trigger_id(self, client, seed_executions):
        """GET /admin/executions?trigger_id=trig-aaa filters by trigger."""
        resp = client.get("/admin/executions?trigger_id=trig-aaa")
        assert resp.status_code == 200
        data = resp.get_json()
        for ex in data["executions"]:
            assert ex["trigger_id"] == "trig-aaa"

    def test_api_filter_by_text_search(self, client, seed_executions):
        """GET /admin/executions?q=security searches output text."""
        resp = client.get("/admin/executions?q=security")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["executions"]) > 0

    def test_api_composed_filter(self, client, seed_executions):
        """GET /admin/executions?status=completed&trigger_id=trig-aaa composes with AND."""
        resp = client.get("/admin/executions?status=completed&trigger_id=trig-aaa")
        assert resp.status_code == 200
        data = resp.get_json()
        for ex in data["executions"]:
            assert ex["status"] == "completed"
            assert ex["trigger_id"] == "trig-aaa"

    def test_api_pagination_with_filter(self, client, seed_executions):
        """GET /admin/executions?status=completed&limit=5&offset=0 paginates filtered results."""
        resp = client.get("/admin/executions?status=completed&limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["executions"]) <= 5
        assert "total_count" in data
        for ex in data["executions"]:
            assert ex["status"] == "completed"
