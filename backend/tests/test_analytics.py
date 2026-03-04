"""Proxy-level tests for analytics aggregation endpoints.

Each test inserts 10+ records into the isolated_db and verifies
that the analytics endpoints return correct aggregated data.
"""

from datetime import datetime, timedelta

from app.db.budgets import create_token_usage_record
from app.db.triggers import add_pr_review, create_execution_log, update_execution_log, update_pr_review


def _date_str(days_ago: int) -> str:
    """Return ISO date string for N days ago."""
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _datetime_str(days_ago: int, hour: int = 12) -> str:
    """Return ISO datetime string for N days ago at given hour."""
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


class TestCostAnalyticsAggregation:
    """Test GET /admin/analytics/cost with 15+ token_usage records."""

    def test_cost_aggregation_by_day(self, client):
        """Insert 15 records across 3 entities and 5 days, verify grouping."""
        entities = [
            ("trigger", "trig-001"),
            ("trigger", "trig-002"),
            ("team", "team-001"),
        ]

        total_inserted_cost = 0.0
        record_count = 0
        for day_offset in range(5):
            for entity_type, entity_id in entities:
                cost = round(0.50 + day_offset * 0.10 + record_count * 0.01, 4)
                create_token_usage_record(
                    execution_id=f"exec-cost-{record_count}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    backend_type="claude",
                    input_tokens=100 + record_count * 10,
                    output_tokens=50 + record_count * 5,
                    total_cost_usd=cost,
                    recorded_at=_datetime_str(day_offset),
                )
                total_inserted_cost += cost
                record_count += 1

        assert record_count == 15

        resp = client.get(
            "/admin/analytics/cost",
            query_string={
                "group_by": "day",
                "start_date": _date_str(10),
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()

        assert "data" in body
        assert "period_count" in body
        assert "total_cost" in body
        assert body["period_count"] == 5
        assert abs(body["total_cost"] - total_inserted_cost) < 0.01

    def test_cost_filter_by_entity_type(self, client):
        """Verify entity_type filter returns only matching records."""
        for i in range(6):
            etype = "trigger" if i < 4 else "team"
            create_token_usage_record(
                execution_id=f"exec-filter-{i}",
                entity_type=etype,
                entity_id=f"{etype}-001",
                backend_type="claude",
                input_tokens=100,
                output_tokens=50,
                total_cost_usd=1.0,
                recorded_at=_datetime_str(0),
            )

        resp = client.get(
            "/admin/analytics/cost",
            query_string={
                "group_by": "day",
                "start_date": _date_str(5),
                "entity_type": "trigger",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()

        # Only trigger records should be included (4 * $1.00)
        assert abs(body["total_cost"] - 4.0) < 0.01


class TestExecutionAnalyticsAggregation:
    """Test GET /admin/analytics/executions with 20+ execution_logs."""

    def test_execution_volume_and_status_counts(self, client):
        """Insert 20 executions with varying statuses, verify counts."""
        statuses = ["success"] * 10 + ["failed"] * 6 + ["cancelled"] * 4
        record_count = 0

        for day_offset in range(4):
            for i in range(5):
                idx = day_offset * 5 + i
                started = _datetime_str(day_offset, hour=10)
                finished = _datetime_str(day_offset, hour=10)  # same time for simplicity
                exec_id = f"exec-analytics-{idx}"

                create_execution_log(
                    execution_id=exec_id,
                    trigger_id="bot-pr-review",
                    trigger_type="github",
                    started_at=started,
                    prompt="test prompt",
                    backend_type="claude",
                    command="claude -p test",
                )

                status = statuses[idx]
                update_execution_log(
                    execution_id=exec_id,
                    status=status,
                    finished_at=finished if status != "cancelled" else None,
                )
                record_count += 1

        assert record_count == 20

        resp = client.get(
            "/admin/analytics/executions",
            query_string={
                "group_by": "day",
                "start_date": _date_str(10),
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()

        assert body["total_executions"] == 20
        assert body["period_count"] == 4

        # Sum up status counts across all periods
        total_success = sum(row["success_count"] for row in body["data"])
        total_failed = sum(row["failed_count"] for row in body["data"])
        total_cancelled = sum(row["cancelled_count"] for row in body["data"])

        assert total_success == 10
        assert total_failed == 6
        assert total_cancelled == 4


class TestEffectivenessAnalytics:
    """Test GET /admin/analytics/effectiveness with 10+ pr_reviews."""

    def test_acceptance_rate_calculation(self, client):
        """Insert 12 PR reviews with varying statuses, verify acceptance_rate."""
        review_statuses = {
            "approved": 4,
            "fixed": 2,
            "changes_requested": 3,  # of these, 1 has fixes_applied=1 (not "ignored")
            "pending": 3,
        }

        review_id_counter = 0
        for status, count in review_statuses.items():
            for i in range(count):
                review_id_counter += 1
                rid = add_pr_review(
                    project_name=f"project-{review_id_counter}",
                    pr_number=review_id_counter,
                    pr_url=f"https://github.com/org/repo/pull/{review_id_counter}",
                    pr_title=f"PR {review_id_counter}",
                    trigger_id="bot-pr-review",
                )
                if rid:
                    update_pr_review(rid, review_status=status)
                    # Make one changes_requested have fixes_applied=1
                    # (so it should NOT count as "ignored")
                    if status == "changes_requested" and i == 0:
                        update_pr_review(rid, fixes_applied=1)

        resp = client.get("/admin/analytics/effectiveness")
        assert resp.status_code == 200
        body = resp.get_json()

        assert body["total_reviews"] == 12
        # accepted = approved(4) + fixed(2) = 6
        assert body["accepted"] == 6
        # ignored = changes_requested with fixes_applied=0 = 2 (3 total minus 1 with fixes)
        assert body["ignored"] == 2
        assert body["pending"] == 3
        # acceptance_rate = 6/12 * 100 = 50.0
        assert body["acceptance_rate"] == 50.0
        assert "over_time" in body


class TestAnalyticsDateFiltering:
    """Test date range filtering across analytics endpoints."""

    def test_cost_date_range_filtering(self, client):
        """Insert records spanning 60 days, query 15-day window."""
        for day_offset in [5, 10, 15, 30, 45, 55]:
            create_token_usage_record(
                execution_id=f"exec-daterange-{day_offset}",
                entity_type="trigger",
                entity_id="trig-dr",
                backend_type="claude",
                input_tokens=100,
                output_tokens=50,
                total_cost_usd=1.0,
                recorded_at=_datetime_str(day_offset),
            )

        # Query window: 20 days ago to 3 days ago
        # Should include: day 5, 10, 15 (3 records)
        # Should exclude: day 30, 45, 55
        resp = client.get(
            "/admin/analytics/cost",
            query_string={
                "group_by": "day",
                "start_date": _date_str(20),
                "end_date": _date_str(3),
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()

        assert body["total_cost"] == 3.0
        assert body["period_count"] == 3


class TestAnalyticsEmptyData:
    """Test analytics endpoints return valid JSON with no data."""

    def test_cost_empty(self, client):
        resp = client.get("/admin/analytics/cost")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["period_count"] == 0
        assert body["total_cost"] == 0.0

    def test_executions_empty(self, client):
        resp = client.get("/admin/analytics/executions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []
        assert body["period_count"] == 0
        assert body["total_executions"] == 0

    def test_effectiveness_empty(self, client):
        resp = client.get("/admin/analytics/effectiveness")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_reviews"] == 0
        assert body["accepted"] == 0
        assert body["ignored"] == 0
        assert body["pending"] == 0
        assert body["acceptance_rate"] == 0.0
        assert body["over_time"] == []
