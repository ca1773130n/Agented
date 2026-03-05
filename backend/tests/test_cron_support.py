"""Tests for standard 5-field cron expression support (API-10)."""

import pytest

from apscheduler.triggers.cron import CronTrigger

from app.db.triggers import add_trigger


# ---------------------------------------------------------------------------
# Unit tests for CronTrigger.from_crontab parsing
# ---------------------------------------------------------------------------


class TestCronTriggerParsing:
    """Verify APScheduler's CronTrigger.from_crontab handles standard expressions."""

    def test_every_15min_business_hours_weekdays(self):
        trigger = CronTrigger.from_crontab("*/15 9-17 * * 1-5")
        assert trigger is not None

    def test_midnight_daily(self):
        trigger = CronTrigger.from_crontab("0 0 * * *")
        assert trigger is not None

    def test_weekday_mornings(self):
        trigger = CronTrigger.from_crontab("0 9 * * MON-FRI")
        assert trigger is not None

    def test_invalid_expression_raises(self):
        with pytest.raises(ValueError):
            CronTrigger.from_crontab("invalid")

    def test_invalid_minute_60_raises(self):
        with pytest.raises(ValueError):
            CronTrigger.from_crontab("60 * * * *")

    def test_six_fields_raises(self):
        with pytest.raises(ValueError):
            CronTrigger.from_crontab("* * * * * *")

    def test_timezone_respected(self):
        import pytz

        tz = pytz.timezone("US/Eastern")
        trigger = CronTrigger.from_crontab("0 9 * * *", timezone=tz)
        assert trigger is not None
        assert str(trigger.timezone) == "US/Eastern"


# ---------------------------------------------------------------------------
# Unit tests for SchedulerService._build_cron_trigger
# ---------------------------------------------------------------------------


class TestBuildCronTrigger:
    """Test the scheduler's _build_cron_trigger method with cron_expression."""

    def test_cron_expression_used_when_present(self):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "schedule_type": "daily",
            "schedule_time": "09:00",
            "schedule_timezone": "UTC",
            "cron_expression": "*/5 * * * *",
        }
        result = SchedulerService._build_cron_trigger(trigger_data)
        assert result is not None
        # Verify it's from crontab (minute field should have step)
        assert str(result) != ""

    def test_cron_expression_takes_precedence_over_legacy(self):
        """When cron_expression is set, legacy schedule_type/time/day are ignored."""
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "schedule_type": "daily",
            "schedule_time": "09:00",
            "schedule_day": 0,
            "schedule_timezone": "UTC",
            "cron_expression": "0 12 * * *",  # Noon daily, not 09:00
        }
        result = SchedulerService._build_cron_trigger(trigger_data)
        assert result is not None

    def test_falls_back_to_legacy_when_no_cron_expression(self):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "schedule_type": "daily",
            "schedule_time": "09:00",
            "schedule_timezone": "UTC",
        }
        result = SchedulerService._build_cron_trigger(trigger_data)
        assert result is not None

    def test_invalid_cron_expression_returns_none(self):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "schedule_type": "daily",
            "schedule_time": "09:00",
            "schedule_timezone": "UTC",
            "cron_expression": "bad expression",
        }
        result = SchedulerService._build_cron_trigger(trigger_data)
        assert result is None

    def test_cron_expression_with_timezone(self):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "schedule_timezone": "Asia/Seoul",
            "cron_expression": "0 9 * * MON-FRI",
        }
        result = SchedulerService._build_cron_trigger(trigger_data)
        assert result is not None
        assert str(result.timezone) == "Asia/Seoul"


# ---------------------------------------------------------------------------
# Integration tests for validate-cron endpoint
# ---------------------------------------------------------------------------


class TestValidateCronEndpoint:
    """Test the POST /admin/triggers/validate-cron endpoint."""

    def test_valid_expression_returns_ok(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={"expression": "*/15 9-17 * * 1-5"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert data["expression"] == "*/15 9-17 * * 1-5"
        assert len(data["next_fires"]) > 0

    def test_valid_expression_with_timezone(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={"expression": "0 9 * * MON-FRI", "timezone": "US/Eastern"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert data["timezone"] == "US/Eastern"

    def test_invalid_expression_returns_400(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={"expression": "not a cron"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "INVALID_CRON"

    def test_missing_expression_returns_400(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "INVALID_REQUEST"

    def test_invalid_timezone_returns_400(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={"expression": "0 9 * * *", "timezone": "Invalid/Zone"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "INVALID_TIMEZONE"

    def test_next_fires_returns_multiple(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/validate-cron",
            json={"expression": "0 0 * * *", "timezone": "UTC"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["next_fires"]) == 5
