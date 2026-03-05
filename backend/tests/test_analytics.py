"""Proxy-level tests for analytics aggregation correctness with real SQLite data."""

from datetime import datetime, timedelta

import pytest

from app.database import (
    add_pr_review,
    add_trigger,
    create_execution_log,
    create_token_usage_record,
    init_db,
    seed_predefined_triggers,
    update_execution_log,
    update_pr_review,
)


@pytest.fixture
def app_client(isolated_db):
    """Create a Flask test client with an isolated database."""
    init_db()
    seed_predefined_triggers()

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _date_ago(days: int) -> str:
    """Return an ISO date string N days ago."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _timestamp_ago(days: int, hours: int = 0) -> str:
    """Return an ISO timestamp N days and hours ago."""
    return (datetime.now() - timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")


class TestCostAnalytics:
    """Test GET /admin/analytics/cost aggregation."""

    def test_cost_analytics_aggregation(self, app_client):
        """Insert 15+ token_usage records across 3 entities and 5 days. Verify grouping."""
        entities = [
            ("trigger", "trig-001"),
            ("team", "team-001"),
            ("project", "proj-001"),
        ]

        total_inserted_cost = 0.0
        record_count = 0
        for i in range(5):  # 5 days
            date_str = _timestamp_ago(i)
            for entity_type, entity_id in entities:
                cost = round(0.10 * (i + 1), 2)
                create_token_usage_record(
                    execution_id=f"exec-cost-{entity_id}-{i}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    backend_type="claude",
                    input_tokens=100 * (i + 1),
                    output_tokens=50 * (i + 1),
                    total_cost_usd=cost,
                    recorded_at=date_str,
                )
                total_inserted_cost += cost
                record_count += 1

        assert record_count == 15

        resp = app_client.get(
            f"/admin/analytics/cost?group_by=day&start_date={_date_ago(10)}"
        )
        assert resp.status_code == 200
        data = resp.get_json()

        assert "data" in data
        assert "period_count" in data
        assert "total_cost" in data

        # Verify total cost matches inserted data
        assert abs(data["total_cost"] - total_inserted_cost) < 0.01

        # Verify we have multiple periods
        assert data["period_count"] >= 1


class TestExecutionAnalytics:
    """Test GET /admin/analytics/executions aggregation."""

    def test_execution_analytics_aggregation(self, app_client):
        """Insert 20+ execution_logs with varying statuses across days."""
        statuses = ["success", "failed", "cancelled", "success", "success"]
        expected_success = 0
        expected_failed = 0
        expected_cancelled = 0
        record_count = 0

        for day in range(4):  # 4 days
            started = _timestamp_ago(day)
            finished = _timestamp_ago(day, hours=-1)  # 1 hour after start
            for j, status in enumerate(statuses):
                exec_id = f"exec-anal-{day}-{j}"
                create_execution_log(
                    execution_id=exec_id,
                    trigger_id="bot-security",
                    trigger_type="webhook",
                    started_at=started,
                    prompt="test prompt",
                    backend_type="claude",
                    command="claude -p test",
                )
                update_execution_log(
                    execution_id=exec_id,
                    status=status,
                    finished_at=finished,
                )
                if status == "success":
                    expected_success += 1
                elif status == "failed":
                    expected_failed += 1
                elif status == "cancelled":
                    expected_cancelled += 1
                record_count += 1

        assert record_count == 20

        resp = app_client.get(
            f"/admin/analytics/executions?group_by=day&start_date={_date_ago(10)}"
        )
        assert resp.status_code == 200
        data = resp.get_json()

        assert "data" in data
        assert "total_executions" in data
        assert data["total_executions"] == 20

        # Verify counts sum up
        total_success = sum(r["success_count"] for r in data["data"])
        total_failed = sum(r["failed_count"] for r in data["data"])
        total_cancelled = sum(r["cancelled_count"] for r in data["data"])

        assert total_success == expected_success
        assert total_failed == expected_failed
        assert total_cancelled == expected_cancelled


class TestEffectivenessAnalytics:
    """Test GET /admin/analytics/effectiveness."""

    def test_effectiveness_analytics(self, app_client):
        """Insert 10+ pr_reviews with varying statuses. Verify acceptance_rate."""
        # Create reviews with different statuses
        review_data = [
            ("approved", 0),   # accepted
            ("approved", 0),   # accepted
            ("approved", 0),   # accepted
            ("fixed", 1),      # accepted (fixed)
            ("fixed", 1),      # accepted (fixed)
            ("changes_requested", 0),  # ignored
            ("changes_requested", 0),  # ignored
            ("changes_requested", 1),  # NOT ignored (fixes applied)
            ("pending", 0),    # pending
            ("pending", 0),    # pending
            ("approved", 0),   # accepted
        ]

        for i, (review_status, fixes_applied) in enumerate(review_data):
            review_id = add_pr_review(
                project_name=f"test-project-{i}",
                pr_number=100 + i,
                pr_url=f"https://github.com/test/repo/pull/{100 + i}",
                pr_title=f"Test PR {i}",
                trigger_id="bot-pr-review",
            )
            assert review_id is not None
            update_pr_review(
                review_id=review_id,
                review_status=review_status,
                fixes_applied=fixes_applied,
            )

        resp = app_client.get("/admin/analytics/effectiveness")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_reviews"] == 11
        # accepted = approved(4) + fixed(2) = 6
        assert data["accepted"] == 6
        # ignored = changes_requested with fixes_applied=0: 2
        assert data["ignored"] == 2
        # pending = 2
        assert data["pending"] == 2
        # acceptance_rate = 6/11 * 100 = 54.5%
        expected_rate = round((6 / 11) * 100, 1)
        assert abs(data["acceptance_rate"] - expected_rate) < 0.2

        # Verify over_time is present
        assert "over_time" in data
        assert isinstance(data["over_time"], list)


class TestDateFiltering:
    """Test analytics date filtering."""

    def test_analytics_date_filtering(self, app_client):
        """Insert records spanning 60 days, query 15-day window. Verify filtering."""
        # Insert records across 60 days
        for i in range(60):
            date_str = _timestamp_ago(i)
            create_token_usage_record(
                execution_id=f"exec-filter-{i}",
                entity_type="trigger",
                entity_id="trig-filter",
                backend_type="claude",
                input_tokens=100,
                output_tokens=50,
                total_cost_usd=0.01,
                recorded_at=date_str,
            )

        # Query only last 15 days
        start = _date_ago(15)
        end = _date_ago(0)
        resp = app_client.get(
            f"/admin/analytics/cost?group_by=day&start_date={start}&end_date={end}"
        )
        assert resp.status_code == 200
        data = resp.get_json()

        # Should have at most 16 periods (days 0-15 inclusive)
        assert data["period_count"] <= 16
        # Total cost should be ~16 * 0.01 = 0.16, not 60 * 0.01 = 0.60
        assert data["total_cost"] < 0.30


class TestEmptyData:
    """Test analytics endpoints with no data."""

    def test_analytics_empty_data(self, app_client):
        """Query all analytics endpoints with empty DB. Verify valid empty responses."""
        # Cost analytics
        resp = app_client.get("/admin/analytics/cost?start_date=2020-01-01")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []
        assert data["period_count"] == 0
        assert data["total_cost"] == 0.0

        # Execution analytics
        resp = app_client.get("/admin/analytics/executions?start_date=2020-01-01")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []
        assert data["total_executions"] == 0

        # Effectiveness analytics
        resp = app_client.get("/admin/analytics/effectiveness")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_reviews"] == 0
        assert data["accepted"] == 0
        assert data["acceptance_rate"] == 0.0
        assert data["over_time"] == []
