"""Health monitoring service for detecting bot health issues.

Runs as an APScheduler background job every 5 minutes. Detects:
- Consecutive execution failures (>= threshold)
- Slow executions (>3x average duration)
- Missing scheduled trigger fires (>2x expected interval)

Alerts are persisted to the health_alerts DB table.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class HealthMonitorService:
    """Periodic bot health check service using APScheduler."""

    _job_id = "bot_health_monitoring"
    _cleanup_job_id = "health_alert_cleanup"
    _last_check_time: Optional[str] = None

    CONSECUTIVE_FAILURE_THRESHOLD = 3
    SLOW_EXECUTION_MULTIPLIER = 3.0
    MISSING_FIRE_MULTIPLIER = 2

    @classmethod
    def init(cls) -> None:
        """Register APScheduler jobs for health monitoring. Called at app startup."""
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            logger.warning("Scheduler not available -- health monitoring jobs not registered")
            return

        # Health check every 5 minutes
        SchedulerService._scheduler.add_job(
            func=cls._check_health,
            trigger="interval",
            minutes=5,
            id=cls._job_id,
            replace_existing=True,
        )

        # Daily cleanup of old alerts (5am UTC)
        from ..db.health_alerts import delete_old_alerts

        SchedulerService._scheduler.add_job(
            func=delete_old_alerts,
            trigger="cron",
            hour=5,
            minute=0,
            id=cls._cleanup_job_id,
            replace_existing=True,
            kwargs={"days": 7},
        )

        logger.info("Health monitor service initialized (5-min interval)")

    @classmethod
    def _check_health(cls) -> None:
        """Main health check loop. Iterates all triggers and checks for issues."""
        from ..db.triggers import get_all_triggers

        now = datetime.now(timezone.utc)
        cls._last_check_time = now.isoformat()

        try:
            triggers = get_all_triggers()
        except Exception as e:
            logger.error("Health check: failed to load triggers: %s", e, exc_info=True)
            return

        for trigger in triggers:
            trigger_id = trigger["id"]
            try:
                cls._check_consecutive_failures(trigger_id)
                cls._check_slow_execution(trigger_id)
                cls._check_missing_fire(trigger)
            except Exception as e:
                logger.error(
                    "Health check failed for trigger %s: %s",
                    trigger_id,
                    e,
                    exc_info=True,
                )

        logger.debug("Health check completed at %s", cls._last_check_time)

    @classmethod
    def _check_consecutive_failures(cls, trigger_id: str) -> None:
        """Check for consecutive execution failures using a simple reverse-chronological loop."""
        from ..db.health_alerts import create_health_alert
        from ..db.triggers import get_execution_logs_for_trigger

        # Get last 10 executions
        logs = get_execution_logs_for_trigger(trigger_id, limit=10)
        if not logs:
            return

        # Count consecutive failures from most recent
        consecutive_failures = 0
        for log in logs:
            if log.get("status") == "failed":
                consecutive_failures += 1
            else:
                break

        if consecutive_failures >= cls.CONSECUTIVE_FAILURE_THRESHOLD:
            create_health_alert(
                alert_type="consecutive_failure",
                trigger_id=trigger_id,
                message=(f"Trigger has {consecutive_failures} consecutive failed executions"),
                details={"consecutive_count": consecutive_failures},
                severity="critical" if consecutive_failures >= 5 else "warning",
            )

    @classmethod
    def _check_slow_execution(cls, trigger_id: str) -> None:
        """Check if the most recent execution is abnormally slow (>3x average)."""
        from ..db.health_alerts import create_health_alert
        from ..db.triggers import get_execution_logs_for_trigger

        # Get last 20 executions
        logs = get_execution_logs_for_trigger(trigger_id, limit=20)
        if len(logs) < 5:
            return  # Not enough history for comparison

        # Calculate average duration from completed executions with duration_ms
        durations = [
            log["duration_ms"]
            for log in logs
            if log.get("duration_ms") is not None and log["duration_ms"] > 0
        ]
        if len(durations) < 5:
            return

        avg_duration = sum(durations) / len(durations)
        if avg_duration <= 0:
            return

        # Check the most recent execution
        most_recent = logs[0]
        recent_duration = most_recent.get("duration_ms")
        if recent_duration is None or recent_duration <= 0:
            return

        if recent_duration > avg_duration * cls.SLOW_EXECUTION_MULTIPLIER:
            create_health_alert(
                alert_type="slow_execution",
                trigger_id=trigger_id,
                message=(
                    f"Latest execution took {recent_duration}ms "
                    f"({recent_duration / avg_duration:.1f}x average of {avg_duration:.0f}ms)"
                ),
                details={
                    "recent_duration_ms": recent_duration,
                    "average_duration_ms": round(avg_duration),
                    "multiplier": round(recent_duration / avg_duration, 1),
                },
                severity="warning",
            )

    @classmethod
    def _check_missing_fire(cls, trigger: dict) -> None:
        """Check if a scheduled trigger has missed its expected fire time.

        Only applies to scheduled triggers (not webhook/github) per 10-RESEARCH.md Pitfall 3.
        """
        if trigger.get("trigger_source") != "scheduled":
            return

        schedule_type = trigger.get("schedule_type")
        if not schedule_type:
            return

        last_run_at = trigger.get("last_run_at")
        if not last_run_at:
            return

        from ..db.health_alerts import create_health_alert

        # Determine expected interval in hours
        interval_hours = {"daily": 24, "weekly": 168, "monthly": 720}.get(schedule_type)
        if not interval_hours:
            return

        try:
            last_run = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
            if not last_run.tzinfo:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return

        now = datetime.now(timezone.utc)
        hours_since_last_run = (now - last_run).total_seconds() / 3600.0

        if hours_since_last_run > interval_hours * cls.MISSING_FIRE_MULTIPLIER:
            create_health_alert(
                alert_type="missing_fire",
                trigger_id=trigger["id"],
                message=(
                    f"Scheduled trigger ({schedule_type}) has not fired "
                    f"in {hours_since_last_run:.0f}h (expected every {interval_hours}h)"
                ),
                details={
                    "schedule_type": schedule_type,
                    "hours_since_last_run": round(hours_since_last_run, 1),
                    "expected_interval_hours": interval_hours,
                    "last_run_at": last_run_at,
                },
                severity="warning",
            )

    @classmethod
    def get_status(cls) -> dict:
        """Return current health status summary."""
        from ..db.health_alerts import get_recent_alerts

        recent = get_recent_alerts(limit=50, acknowledged=False)
        critical_count = sum(1 for a in recent if a.get("severity") == "critical")
        warning_count = sum(1 for a in recent if a.get("severity") == "warning")

        return {
            "total_alerts": len(recent),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "last_check_time": cls._last_check_time,
        }
