"""Scheduler service for running scheduled triggers and teams using APScheduler."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..utils.timezone import get_local_timezone

try:
    import pytz
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    BackgroundScheduler = None
    CronTrigger = None
    pytz = None

from ..database import (
    delete_old_execution_logs,
    get_team,
    get_teams_by_trigger_source,
    get_trigger,
    get_triggers_by_trigger_source,
    update_trigger_last_run,
    update_trigger_next_run,
)

logger = logging.getLogger(__name__)


class SchedulerService:
    """Service for managing scheduled trigger and team executions."""

    _scheduler: Optional["BackgroundScheduler"] = None
    _initialized: bool = False

    @classmethod
    def init(cls, app=None):
        """Initialize the scheduler. Should be called once at app startup."""
        if not SCHEDULER_AVAILABLE:
            logger.warning("APScheduler not installed. Scheduled triggers will not run.")
            return

        if cls._initialized:
            return

        cls._scheduler = BackgroundScheduler(
            timezone=pytz.UTC,
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Only one instance of a job at a time
            },
        )
        cls._scheduler.start()
        cls._initialized = True

        # Load all scheduled triggers and teams
        cls._load_scheduled_triggers()
        cls._load_scheduled_teams()

        # Schedule daily cleanup of old execution logs (30-day retention)
        cls._scheduler.add_job(
            func=delete_old_execution_logs,
            trigger="cron",
            hour=3,
            minute=0,
            id="cleanup_old_executions",
            replace_existing=True,
            kwargs={"days": 30},
        )
        logger.info("Scheduled daily execution log cleanup (30-day retention)")

        # Initialize workflow trigger service (depends on scheduler being started)
        try:
            from .workflow_trigger_service import WorkflowTriggerService

            WorkflowTriggerService.init()
        except Exception as e:
            logger.error(f"Error initializing workflow trigger service: {e}")

        logger.info("Scheduler service initialized")

    @classmethod
    def shutdown(cls):
        """Shutdown the scheduler gracefully."""
        if cls._scheduler and cls._initialized:
            cls._scheduler.shutdown(wait=False)
            cls._initialized = False
            logger.info("Scheduler service shutdown")

    @classmethod
    def _load_scheduled_triggers(cls):
        """Load all scheduled triggers and register their jobs."""
        if not cls._scheduler:
            return

        triggers = get_triggers_by_trigger_source("scheduled")
        for trigger in triggers:
            if trigger.get("enabled") and trigger.get("schedule_type"):
                cls.schedule_trigger(trigger)
                logger.info(f"Loaded scheduled trigger: {trigger['id']} ({trigger['name']})")

    @classmethod
    def schedule_trigger(cls, trigger_data: dict):
        """Schedule a trigger based on its configuration."""
        if not cls._scheduler:
            return

        trigger_id = trigger_data["id"]
        job_id = f"trigger-{trigger_id}"

        # Remove existing job if any
        existing_job = cls._scheduler.get_job(job_id)
        if existing_job:
            cls._scheduler.remove_job(job_id)

        # Only schedule if trigger has valid schedule config
        schedule_type = trigger_data.get("schedule_type")
        if not schedule_type:
            return

        cron_trigger = cls._build_cron_trigger(trigger_data)
        if not cron_trigger:
            logger.warning(f"Could not build cron trigger for trigger {trigger_id}")
            return

        # Add the job
        cls._scheduler.add_job(
            cls._execute_trigger,
            trigger=cron_trigger,
            id=job_id,
            args=[trigger_id],
            replace_existing=True,
            name=f"Scheduled: {trigger_data.get('name', trigger_id)}",
        )

        # Update next_run_at in database
        job = cls._scheduler.get_job(job_id)
        if job and job.next_run_time:
            update_trigger_next_run(trigger_id, job.next_run_time.isoformat())
            logger.info(f"Scheduled trigger {trigger_id} - next run: {job.next_run_time}")

    @classmethod
    def unschedule_trigger(cls, trigger_id: str):
        """Remove a trigger from the scheduler."""
        if not cls._scheduler:
            return

        job_id = f"trigger-{trigger_id}"
        existing_job = cls._scheduler.get_job(job_id)
        if existing_job:
            cls._scheduler.remove_job(job_id)
            # Clear next_run_at
            update_trigger_next_run(trigger_id, None)
            logger.info(f"Unscheduled trigger {trigger_id}")

    @classmethod
    def reschedule_trigger(cls, trigger_id: str):
        """Reschedule a trigger after its configuration changes."""
        trigger_data = get_trigger(trigger_id)
        if not trigger_data:
            return

        if trigger_data.get("trigger_source") == "scheduled" and trigger_data.get("enabled"):
            cls.schedule_trigger(trigger_data)
        else:
            cls.unschedule_trigger(trigger_id)

    @classmethod
    def _build_cron_trigger(cls, trigger_data: dict) -> Optional["CronTrigger"]:
        """Build APScheduler CronTrigger from trigger schedule config."""
        schedule_type = trigger_data.get("schedule_type")
        schedule_time = trigger_data.get("schedule_time", "00:00")
        schedule_day = trigger_data.get("schedule_day", 0)
        timezone_str = trigger_data.get("schedule_timezone") or get_local_timezone()

        try:
            tz = pytz.timezone(timezone_str)
        except Exception:
            tz = pytz.UTC

        # Parse time
        try:
            hour, minute = map(int, schedule_time.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 0, 0

        if schedule_type == "daily":
            return CronTrigger(hour=hour, minute=minute, timezone=tz)
        elif schedule_type == "weekly":
            # schedule_day: 0=Monday, 6=Sunday in APScheduler
            return CronTrigger(day_of_week=schedule_day, hour=hour, minute=minute, timezone=tz)
        elif schedule_type == "monthly":
            # schedule_day: 1-31 for day of month
            return CronTrigger(day=schedule_day or 1, hour=hour, minute=minute, timezone=tz)

        return None

    @classmethod
    def _execute_trigger(cls, trigger_id: str):
        """Execute a scheduled trigger. Called by APScheduler."""
        logger.info(f"Executing scheduled trigger: {trigger_id}")

        # Update last_run_at
        update_trigger_last_run(trigger_id, datetime.now(timezone.utc).isoformat())

        trigger_data = get_trigger(trigger_id)
        if not trigger_data:
            logger.error(f"Trigger not found: {trigger_id}")
            return

        if not trigger_data.get("enabled"):
            logger.info(f"Trigger {trigger_id} is disabled, skipping execution")
            return

        try:
            # Import here to avoid circular imports
            from .execution_service import ExecutionService

            # Run the trigger with trigger_type="scheduled"
            ExecutionService.run_trigger(
                trigger=trigger_data,
                message_text="Scheduled execution",
                event={"trigger_type": "scheduled"},
                trigger_type="scheduled",
            )
            logger.info(f"Scheduled trigger {trigger_id} execution completed")
        except Exception as e:
            logger.error(f"Error executing scheduled trigger {trigger_id}: {e}")

        # Update next_run_at after execution
        if cls._scheduler:
            job = cls._scheduler.get_job(f"trigger-{trigger_id}")
            if job and job.next_run_time:
                update_trigger_next_run(trigger_id, job.next_run_time.isoformat())

    @classmethod
    def get_job_info(cls, trigger_id: str) -> Optional[dict]:
        """Get information about a scheduled job."""
        if not cls._scheduler:
            return None

        job = cls._scheduler.get_job(f"trigger-{trigger_id}")
        if not job:
            return None

        return {
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }

    @classmethod
    def list_jobs(cls) -> list:
        """List all scheduled jobs."""
        if not cls._scheduler:
            return []

        jobs = []
        for job in cls._scheduler.get_jobs():
            jobs.append(
                {
                    "job_id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs

    # =========================================================================
    # Team scheduling
    # =========================================================================

    @classmethod
    def _load_scheduled_teams(cls):
        """Load all scheduled teams and register their jobs."""
        if not cls._scheduler:
            return

        teams = get_teams_by_trigger_source("scheduled")
        for team in teams:
            if team.get("enabled"):
                cls.schedule_team(team)
                logger.info(f"Loaded scheduled team: {team['id']} ({team['name']})")

    @classmethod
    def schedule_team(cls, team: dict):
        """Schedule a team based on its trigger_config.

        Trigger config follows the same schema as trigger scheduling:
        {"schedule_type": "daily|weekly|monthly", "schedule_time": "HH:MM",
         "schedule_day": int, "schedule_timezone": "Asia/Seoul"}
        """
        if not cls._scheduler:
            return

        team_id = team["id"]
        job_id = f"team_{team_id}"

        # Remove existing job if any
        existing_job = cls._scheduler.get_job(job_id)
        if existing_job:
            cls._scheduler.remove_job(job_id)

        # Parse trigger_config for schedule fields
        trigger_config = team.get("trigger_config")
        if trigger_config and isinstance(trigger_config, str):
            try:
                trigger_config = json.loads(trigger_config)
            except (json.JSONDecodeError, TypeError):
                trigger_config = {}
        if not trigger_config:
            return

        schedule_type = trigger_config.get("schedule_type")
        if not schedule_type:
            return

        # Build a schedule dict for _build_cron_trigger compatibility
        schedule_dict = {
            "schedule_type": schedule_type,
            "schedule_time": trigger_config.get("schedule_time", "00:00"),
            "schedule_day": trigger_config.get("schedule_day", 0),
            "schedule_timezone": trigger_config.get("schedule_timezone") or get_local_timezone(),
        }

        cron_trigger = cls._build_cron_trigger(schedule_dict)
        if not cron_trigger:
            logger.warning(f"Could not build trigger for team {team_id}")
            return

        cls._scheduler.add_job(
            cls._execute_team,
            trigger=cron_trigger,
            id=job_id,
            args=[team_id],
            replace_existing=True,
            name=f"Scheduled team: {team.get('name', team_id)}",
        )

        job = cls._scheduler.get_job(job_id)
        if job and job.next_run_time:
            logger.info(f"Scheduled team {team_id} - next run: {job.next_run_time}")

    @classmethod
    def unschedule_team(cls, team_id: str):
        """Remove a team from the scheduler."""
        if not cls._scheduler:
            return

        job_id = f"team_{team_id}"
        existing_job = cls._scheduler.get_job(job_id)
        if existing_job:
            cls._scheduler.remove_job(job_id)
            logger.info(f"Unscheduled team {team_id}")

    @classmethod
    def _execute_team(cls, team_id: str):
        """Execute a scheduled team. Called by APScheduler."""
        logger.info(f"Executing scheduled team: {team_id}")

        team = get_team(team_id)
        if not team:
            logger.error(f"Team not found: {team_id}")
            return

        if not team.get("enabled", 1):
            logger.info(f"Team {team_id} is disabled, skipping execution")
            return

        try:
            from .team_execution_service import TeamExecutionService

            TeamExecutionService.execute_team(
                team_id=team_id,
                message="Scheduled execution",
                event={"trigger_type": "scheduled"},
                trigger_type="scheduled",
            )
            logger.info(f"Scheduled team {team_id} execution started")
        except Exception as e:
            logger.error(f"Error executing scheduled team {team_id}: {e}")
