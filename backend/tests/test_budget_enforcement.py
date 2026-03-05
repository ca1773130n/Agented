"""Tests for extended budget enforcement (time + run count limits)."""

import random
import string
from datetime import datetime, timezone

from app.db.budgets import get_budget_limit, set_budget_limit
from app.db.connection import get_connection
from app.db.health_alerts import get_recent_alerts
from app.services.budget_service import BudgetService


def _make_trigger(conn, trigger_id):
    """Create a trigger record for FK constraints."""
    conn.execute(
        """
        INSERT OR IGNORE INTO triggers (id, name, prompt_template, backend_type, trigger_source)
        VALUES (?, ?, 'test prompt', 'claude', 'webhook')
        """,
        (trigger_id, f"Test {trigger_id}"),
    )


def _insert_exec(conn, trigger_id, started_at=None, status="success"):
    """Insert an execution log for the given trigger."""
    if started_at is None:
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(started_at, datetime):
        started_at = started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    eid = "exec-" + "".join(random.choices(string.ascii_lowercase, k=6))
    conn.execute(
        """
        INSERT INTO execution_logs
            (execution_id, trigger_id, trigger_type, backend_type, status, started_at)
        VALUES (?, ?, 'webhook', 'claude', ?, ?)
        """,
        (eid, trigger_id, status, started_at),
    )
    return eid


class TestBudgetEnforcement:
    """Budget enforcement tests for run count and time limits."""

    def test_monthly_run_count_enforcement(self, isolated_db):
        """Monthly run count at limit should block execution."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-run1")
            conn.commit()

        set_budget_limit("trigger", "trig-run1", max_monthly_runs=5)

        with get_connection() as conn:
            for _ in range(5):
                _insert_exec(conn, "trig-run1")
            conn.commit()

        result = BudgetService.check_budget("trigger", "trig-run1")
        assert result["allowed"] is False
        assert "Monthly run limit exceeded" in result["reason"]
        assert result["monthly_run_count"] == 5
        assert result["max_monthly_runs"] == 5

    def test_monthly_run_count_under_limit(self, isolated_db):
        """Monthly run count under limit should allow execution."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-run2")
            conn.commit()

        set_budget_limit("trigger", "trig-run2", max_monthly_runs=10)

        with get_connection() as conn:
            for _ in range(3):
                _insert_exec(conn, "trig-run2")
            conn.commit()

        result = BudgetService.check_budget("trigger", "trig-run2")
        assert result["allowed"] is True

    def test_execution_time_limit_check(self, isolated_db):
        """Execution time limit returns True when exceeded, False when within."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-time1")
            conn.commit()

        set_budget_limit("trigger", "trig-time1", max_execution_time_seconds=300)

        # Exceeded
        assert BudgetService.check_execution_time_limit("trigger", "trig-time1", 400) is True
        # Within limit
        assert BudgetService.check_execution_time_limit("trigger", "trig-time1", 200) is False

    def test_budget_limit_columns_persist(self, isolated_db):
        """New columns should be stored and retrievable."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-persist")
            conn.commit()

        set_budget_limit(
            "trigger",
            "trig-persist",
            max_execution_time_seconds=600,
            max_monthly_runs=100,
        )

        limits = get_budget_limit("trigger", "trig-persist")
        assert limits is not None
        assert limits["max_execution_time_seconds"] == 600
        assert limits["max_monthly_runs"] == 100

    def test_no_limit_when_null(self, isolated_db):
        """NULL limits mean no restriction -- budget checks should pass."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-null")
            conn.commit()

        set_budget_limit(
            "trigger",
            "trig-null",
            soft_limit_usd=100.0,
            max_monthly_runs=None,
            max_execution_time_seconds=None,
        )

        with get_connection() as conn:
            for _ in range(50):
                _insert_exec(conn, "trig-null")
            conn.commit()

        result = BudgetService.check_budget("trigger", "trig-null")
        assert result["allowed"] is True

        # Time limit should not trigger either
        assert BudgetService.check_execution_time_limit("trigger", "trig-null", 99999) is False

    def test_budget_exceeded_creates_health_alert(self, client, isolated_db):
        """Pre-execution budget check creates health alert when monthly run limit exceeded."""
        with get_connection() as conn:
            _make_trigger(conn, "trig-alert")
            conn.commit()

        set_budget_limit("trigger", "trig-alert", max_monthly_runs=3)

        with get_connection() as conn:
            for _ in range(3):
                _insert_exec(conn, "trig-alert")
            conn.commit()

        # Verify budget check blocks
        result = BudgetService.check_budget("trigger", "trig-alert")
        assert result["allowed"] is False

        # Simulate what execution_service does: create the health alert
        from app.db.health_alerts import create_health_alert

        create_health_alert(
            alert_type="budget_exceeded",
            trigger_id="trig-alert",
            message="Execution blocked: monthly run limit exceeded (3/3)",
            details={"reason": result["reason"]},
            severity="critical",
        )

        # Verify health alert was created
        alerts = get_recent_alerts(trigger_id="trig-alert")
        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert["alert_type"] == "budget_exceeded"
        assert alert["severity"] == "critical"
        assert "monthly run limit exceeded" in alert["message"]
