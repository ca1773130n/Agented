"""Tests for health monitoring service and report generation.

Uses isolated_db fixture for real SQLite data -- no mocking of the DB layer.
"""

from datetime import datetime, timedelta, timezone

from app.db.health_alerts import get_recent_alerts
from app.db.triggers import (
    add_pr_review,
    create_trigger,
    create_execution_log,
    update_execution_log,
    update_pr_review,
)
from app.services.health_monitor_service import HealthMonitorService
from app.services.report_service import ReportService


def _create_trigger(name="test-trigger", trigger_source="webhook", **kwargs):
    """Helper to create a trigger and return its ID."""
    return create_trigger(
        name=name,
        prompt_template="test {paths}",
        trigger_source=trigger_source,
        **kwargs,
    )


def _create_execution(trigger_id, status="completed", duration_ms=60000, offset_hours=0):
    """Helper to create an execution log with given status and duration."""
    import uuid

    exec_id = f"exec-{uuid.uuid4().hex[:8]}"
    started = (datetime.now(timezone.utc) - timedelta(hours=offset_hours)).isoformat()
    finished = (
        datetime.now(timezone.utc)
        - timedelta(hours=offset_hours)
        + timedelta(milliseconds=duration_ms)
    ).isoformat()

    create_execution_log(
        execution_id=exec_id,
        trigger_id=trigger_id,
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
        duration_ms=duration_ms,
    )
    return exec_id


# ===========================================================================
# Detection logic tests
# ===========================================================================


def test_consecutive_failure_detection(isolated_db):
    """5 consecutive failed executions should trigger a consecutive_failure alert."""
    trigger_id = _create_trigger(name="fail-bot")

    # Create 5 failed executions (most recent first when queried)
    for i in range(5):
        _create_execution(trigger_id, status="failed", offset_hours=i)

    HealthMonitorService._check_consecutive_failures(trigger_id)

    alerts = get_recent_alerts(trigger_id=trigger_id)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "consecutive_failure"
    assert "5 consecutive" in alerts[0]["message"]


def test_no_false_positive_on_mixed_results(isolated_db):
    """Mixed pass/fail results should NOT trigger consecutive failure alert."""
    trigger_id = _create_trigger(name="mixed-bot")

    # Create: 2 failed, 1 success, 2 failed (newest first in query order)
    # offset_hours=0 is most recent
    _create_execution(trigger_id, status="failed", offset_hours=0)
    _create_execution(trigger_id, status="failed", offset_hours=1)
    _create_execution(trigger_id, status="completed", offset_hours=2)
    _create_execution(trigger_id, status="failed", offset_hours=3)
    _create_execution(trigger_id, status="failed", offset_hours=4)

    HealthMonitorService._check_consecutive_failures(trigger_id)

    alerts = get_recent_alerts(trigger_id=trigger_id)
    assert len(alerts) == 0, "Success in the middle should break consecutive streak"


def test_slow_execution_detection(isolated_db):
    """Execution >3x average duration should trigger a slow_execution alert."""
    trigger_id = _create_trigger(name="slow-bot")

    # Create 10 executions with ~5 minute average (300000 ms)
    for i in range(10):
        _create_execution(trigger_id, status="completed", duration_ms=300000, offset_hours=i + 1)

    # Create one very slow recent execution: 20 minutes (1200000 ms) = 4x average
    _create_execution(trigger_id, status="completed", duration_ms=1200000, offset_hours=0)

    HealthMonitorService._check_slow_execution(trigger_id)

    alerts = get_recent_alerts(trigger_id=trigger_id)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "slow_execution"


def test_missing_fire_scheduled_only(isolated_db):
    """Missing fire should only alert for scheduled triggers, not webhook."""
    # Scheduled trigger with last_run 3 days ago (>2x daily interval)
    scheduled_id = _create_trigger(
        name="scheduled-bot",
        trigger_source="scheduled",
        schedule_type="daily",
        schedule_time="09:00",
    )

    # Manually set last_run_at to 3 days ago
    from app.db.triggers import update_trigger_last_run

    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    update_trigger_last_run(scheduled_id, three_days_ago)

    # Reload trigger data for the check
    from app.db.triggers import get_trigger

    scheduled_trigger = get_trigger(scheduled_id)
    HealthMonitorService._check_missing_fire(scheduled_trigger)

    alerts = get_recent_alerts(trigger_id=scheduled_id)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "missing_fire"

    # Webhook trigger with stale last_run should NOT alert
    webhook_id = _create_trigger(name="webhook-bot", trigger_source="webhook")
    update_trigger_last_run(webhook_id, three_days_ago)
    webhook_trigger = get_trigger(webhook_id)
    HealthMonitorService._check_missing_fire(webhook_trigger)

    webhook_alerts = get_recent_alerts(trigger_id=webhook_id)
    assert len(webhook_alerts) == 0, "Webhook triggers should not get missing_fire alerts"


def test_alert_deduplication(isolated_db):
    """Running health check twice within 30 min should only create 1 alert."""
    trigger_id = _create_trigger(name="dedup-bot")

    # Create enough failures
    for i in range(5):
        _create_execution(trigger_id, status="failed", offset_hours=i)

    # First check
    HealthMonitorService._check_consecutive_failures(trigger_id)
    alerts1 = get_recent_alerts(trigger_id=trigger_id)
    assert len(alerts1) == 1

    # Second check (within 30 minutes)
    HealthMonitorService._check_consecutive_failures(trigger_id)
    alerts2 = get_recent_alerts(trigger_id=trigger_id)
    assert len(alerts2) == 1, "Duplicate alert should be prevented by 30-min dedup window"


# ===========================================================================
# Report generation tests
# ===========================================================================


def test_weekly_report_generation(isolated_db):
    """Report should include correct counts for PRs, issues, and top bots."""
    # Create a trigger with GitHub executions
    trigger_id = _create_trigger(name="pr-review-bot", trigger_source="github")

    # Create 3 completed GitHub executions
    import uuid

    for i in range(3):
        exec_id = f"exec-{uuid.uuid4().hex[:8]}"
        create_execution_log(
            execution_id=exec_id,
            trigger_id=trigger_id,
            trigger_type="github",
            started_at=datetime.now(timezone.utc).isoformat(),
            prompt="review PR",
            backend_type="claude",
            command="claude -p review",
        )
        update_execution_log(execution_id=exec_id, status="completed", duration_ms=30000)

    # Create a PR review with changes_requested
    add_pr_review(
        project_name="test-project",
        pr_number=1,
        pr_url="https://github.com/test/repo/pull/1",
        pr_title="Test PR",
        trigger_id=trigger_id,
    )
    # Get the review and update it
    from app.db.triggers import get_pr_reviews_for_trigger

    reviews = get_pr_reviews_for_trigger(trigger_id=trigger_id)
    if reviews:
        update_pr_review(reviews[0]["id"], review_status="changes_requested")

    # Create a failing trigger for bots_needing_attention
    fail_trigger_id = _create_trigger(name="always-fail-bot")
    for i in range(4):
        _create_execution(fail_trigger_id, status="failed", offset_hours=0)
    _create_execution(fail_trigger_id, status="completed", offset_hours=0)

    report = ReportService.generate_weekly_report()

    assert report["prs_reviewed"] == 3
    assert report["issues_found"] == 1
    assert report["estimated_time_saved_minutes"] > 0
    assert len(report["top_bots"]) > 0
    assert report["period_start"] != ""
    assert report["period_end"] != ""

    # Check bots_needing_attention has the failing trigger (4/5 = 80% failure)
    attention_ids = [b["trigger_id"] for b in report["bots_needing_attention"]]
    assert fail_trigger_id in attention_ids


def test_report_empty_data(isolated_db):
    """Report with no data should return valid structure with zero counts."""
    report = ReportService.generate_weekly_report()

    assert report["prs_reviewed"] == 0
    assert report["issues_found"] == 0
    assert report["estimated_time_saved_minutes"] == 0
    assert report["top_bots"] == []
    assert report["bots_needing_attention"] == []
    assert report["period_start"] != ""
    assert report["period_end"] != ""
