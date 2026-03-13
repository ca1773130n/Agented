"""Scheduler service for running scheduled triggers and teams using APScheduler.

The public API is provided by ``SchedulerService`` (init, shutdown, schedule_*,
unschedule_*, list_jobs, etc.).  Internally the class delegates to focused helper
methods grouped into four areas:

1. **Startup** — ``_create_scheduler``, ``_schedule_log_cleanup``,
   ``_init_workflow_triggers``
2. **Trigger scheduling** — ``_load_scheduled_triggers``, ``schedule_trigger``,
   ``unschedule_trigger``, ``reschedule_trigger``, ``_execute_trigger``
3. **Team scheduling** — ``_load_scheduled_teams``, ``schedule_team``,
   ``unschedule_team``, ``_execute_team``
4. **Cron helpers** — ``_build_cron_trigger``, ``_resolve_timezone``,
   ``_parse_time``, ``_build_legacy_cron_trigger``
"""

import json
import logging
import os
import time
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

    # =========================================================================
    # Startup / shutdown
    # =========================================================================

    @classmethod
    def init(cls, app=None) -> None:
        """Initialize the scheduler. Should be called once at app startup."""
        if not SCHEDULER_AVAILABLE:
            logger.warning("APScheduler not installed. Scheduled triggers will not run.")
            return

        if cls._initialized:
            return

        cls._create_scheduler()
        cls._load_scheduled_triggers()
        cls._load_scheduled_teams()
        cls._schedule_log_cleanup()
        cls._init_workflow_triggers()

        logger.info("Scheduler service initialized")

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown the scheduler gracefully."""
        if cls._scheduler and cls._initialized:
            cls._scheduler.shutdown(wait=False)
            cls._initialized = False
            logger.info("Scheduler service shutdown")

    @classmethod
    def _create_scheduler(cls) -> None:
        """Create and start the APScheduler BackgroundScheduler."""
        cls._scheduler = BackgroundScheduler(
            timezone=pytz.UTC,
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Only one instance of a job at a time
            },
        )
        cls._scheduler.start()
        cls._initialized = True

    @classmethod
    def _schedule_log_cleanup(cls) -> None:
        """Schedule daily cleanup of old execution logs if retention is configured.

        Default: 0 = unlimited retention (no cleanup). Set EXECUTION_LOG_RETENTION_DAYS
        to a positive integer to enable automatic cleanup.
        """
        retention_days = int(os.environ.get("EXECUTION_LOG_RETENTION_DAYS", "0"))
        if retention_days > 0:
            cls._scheduler.add_job(
                func=delete_old_execution_logs,
                trigger="cron",
                hour=3,
                minute=0,
                id="cleanup_old_executions",
                replace_existing=True,
                kwargs={"days": retention_days},
            )
            logger.info("Scheduled daily execution log cleanup (%d-day retention)", retention_days)
        else:
            logger.info(
                "Execution log cleanup disabled (EXECUTION_LOG_RETENTION_DAYS=0, unlimited retention)"
            )

    @classmethod
    def _init_workflow_triggers(cls) -> None:
        """Initialize workflow trigger service (depends on scheduler being started)."""
        try:
            from .workflow_trigger_service import WorkflowTriggerService

            WorkflowTriggerService.init()
        except Exception as e:
            logger.error(f"Error initializing workflow trigger service: {e}", exc_info=True)

    # =========================================================================
    # Trigger scheduling
    # =========================================================================

    @classmethod
    def _load_scheduled_triggers(cls) -> None:
        """Load all scheduled triggers and register their jobs."""
        if not cls._scheduler:
            return

        triggers = get_triggers_by_trigger_source("scheduled")
        for trigger in triggers:
            if trigger.get("enabled") and trigger.get("schedule_type"):
                cls.schedule_trigger(trigger)
                logger.info(f"Loaded scheduled trigger: {trigger['id']} ({trigger['name']})")

    @classmethod
    def schedule_trigger(cls, trigger_data: dict) -> None:
        """Schedule a trigger based on its configuration."""
        if not cls._scheduler:
            return

        trigger_id = trigger_data["id"]
        job_id = f"trigger-{trigger_id}"

        cls._remove_job_if_exists(job_id)

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
        cls._sync_next_run(job_id, trigger_id)

    @classmethod
    def unschedule_trigger(cls, trigger_id: str) -> None:
        """Remove a trigger from the scheduler."""
        if not cls._scheduler:
            return

        job_id = f"trigger-{trigger_id}"
        if cls._remove_job_if_exists(job_id):
            # Clear next_run_at
            update_trigger_next_run(trigger_id, None)
            logger.info(f"Unscheduled trigger {trigger_id}")

    @classmethod
    def reschedule_trigger(cls, trigger_id: str) -> None:
        """Reschedule a trigger after its configuration changes."""
        trigger_data = get_trigger(trigger_id)
        if not trigger_data:
            return

        if trigger_data.get("trigger_source") == "scheduled" and trigger_data.get("enabled"):
            cls.schedule_trigger(trigger_data)
        else:
            cls.unschedule_trigger(trigger_id)

    @classmethod
    def _execute_trigger(cls, trigger_id: str) -> None:
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

        if trigger_data.get("dispatch_type") == "super_agent" and trigger_data.get(
            "super_agent_id"
        ):
            try:
                from .super_agent_session_service import (
                    SessionLimitError,
                    SuperAgentSessionService,
                )
                from ..db.triggers import create_execution_log

                session_id = SuperAgentSessionService.get_or_create_session(
                    trigger_data["super_agent_id"]
                )
                SuperAgentSessionService.send_message(
                    session_id, trigger_data["prompt_template"]
                )
                exec_id = f"exec-{trigger_id}-{int(time.time())}"
                create_execution_log(
                    execution_id=exec_id,
                    trigger_id=trigger_id,
                    trigger_type="scheduled",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    prompt=trigger_data["prompt_template"],
                    backend_type=trigger_data.get("backend_type", "claude"),
                    command="",
                    source_type="super_agent",
                    session_id=session_id,
                )
            except SessionLimitError as e:
                logger.warning(f"Scheduled trigger {trigger_id} session limit: {e}")
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
            logger.error(f"Error executing scheduled trigger {trigger_id}: {e}", exc_info=True)

        # Update next_run_at after execution
        cls._sync_next_run(f"trigger-{trigger_id}", trigger_id)

    # =========================================================================
    # Team scheduling
    # =========================================================================

    @classmethod
    def _load_scheduled_teams(cls) -> None:
        """Load all scheduled teams and register their jobs."""
        if not cls._scheduler:
            return

        teams = get_teams_by_trigger_source("scheduled")
        for team in teams:
            if team.get("enabled"):
                cls.schedule_team(team)
                logger.info(f"Loaded scheduled team: {team['id']} ({team['name']})")

    @classmethod
    def schedule_team(cls, team: dict) -> None:
        """Schedule a team based on its trigger_config.

        Trigger config follows the same schema as trigger scheduling:
        {"schedule_type": "daily|weekly|monthly", "schedule_time": "HH:MM",
         "schedule_day": int, "schedule_timezone": "Asia/Seoul"}
        """
        if not cls._scheduler:
            return

        team_id = team["id"]
        job_id = f"team_{team_id}"

        cls._remove_job_if_exists(job_id)

        trigger_config = cls._parse_trigger_config(team.get("trigger_config"))
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
    def unschedule_team(cls, team_id: str) -> None:
        """Remove a team from the scheduler."""
        if not cls._scheduler:
            return

        job_id = f"team_{team_id}"
        if cls._remove_job_if_exists(job_id):
            logger.info(f"Unscheduled team {team_id}")

    @classmethod
    def _execute_team(cls, team_id: str) -> None:
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
            logger.error(f"Error executing scheduled team {team_id}: {e}", exc_info=True)

    # =========================================================================
    # Cron helpers
    # =========================================================================

    @classmethod
    def _build_cron_trigger(cls, trigger_data: dict) -> Optional["CronTrigger"]:
        """Build APScheduler CronTrigger from trigger schedule config.

        If ``cron_expression`` is present, it takes precedence over the legacy
        structured schedule fields (schedule_type/schedule_time/schedule_day).
        """
        tz = cls._resolve_timezone(trigger_data.get("schedule_timezone"))

        # Prefer cron_expression if provided (standard 5-field cron syntax)
        cron_expr = trigger_data.get("cron_expression")
        if cron_expr:
            try:
                return CronTrigger.from_crontab(cron_expr, timezone=tz)
            except (ValueError, TypeError) as e:
                logger.warning("Invalid cron expression %r for trigger: %s", cron_expr, e)
                return None

        # Fall back to legacy structured schedule fields
        return cls._build_legacy_cron_trigger(trigger_data, tz)

    @classmethod
    def _resolve_timezone(cls, timezone_str: Optional[str]):
        """Resolve a timezone string to a pytz timezone, falling back to UTC."""
        timezone_str = timezone_str or get_local_timezone()
        try:
            return pytz.timezone(timezone_str)
        except Exception:
            return pytz.UTC

    @classmethod
    def _parse_time(cls, schedule_time: str) -> tuple[int, int]:
        """Parse an 'HH:MM' time string, returning (hour, minute). Defaults to (0, 0)."""
        try:
            hour, minute = map(int, schedule_time.split(":"))
            return hour, minute
        except (ValueError, AttributeError):
            return 0, 0

    @classmethod
    def _build_legacy_cron_trigger(cls, trigger_data: dict, tz) -> Optional["CronTrigger"]:
        """Build a CronTrigger from legacy schedule_type/schedule_time/schedule_day fields."""
        schedule_type = trigger_data.get("schedule_type")
        schedule_time = trigger_data.get("schedule_time", "00:00")
        schedule_day = trigger_data.get("schedule_day", 0)

        hour, minute = cls._parse_time(schedule_time)

        if schedule_type == "daily":
            return CronTrigger(hour=hour, minute=minute, timezone=tz)
        elif schedule_type == "weekly":
            # schedule_day: 0=Monday, 6=Sunday in APScheduler
            return CronTrigger(day_of_week=schedule_day, hour=hour, minute=minute, timezone=tz)
        elif schedule_type == "monthly":
            # schedule_day: 1-31 for day of month
            return CronTrigger(day=schedule_day or 1, hour=hour, minute=minute, timezone=tz)

        return None

    # =========================================================================
    # Job introspection
    # =========================================================================

    @classmethod
    def get_job_info(cls, trigger_id: str) -> Optional[dict]:
        """Get information about a scheduled job."""
        if not cls._scheduler:
            return None

        job = cls._scheduler.get_job(f"trigger-{trigger_id}")
        if not job:
            return None

        return cls._job_to_dict(job)

    @classmethod
    def list_jobs(cls) -> list:
        """List all scheduled jobs."""
        if not cls._scheduler:
            return []

        return [cls._job_to_dict(job) for job in cls._scheduler.get_jobs()]

    # =========================================================================
    # Internal utilities
    # =========================================================================

    @classmethod
    def _remove_job_if_exists(cls, job_id: str) -> bool:
        """Remove a job by id if it exists. Returns True if a job was removed."""
        if not cls._scheduler:
            return False
        existing_job = cls._scheduler.get_job(job_id)
        if existing_job:
            cls._scheduler.remove_job(job_id)
            return True
        return False

    @classmethod
    def _sync_next_run(cls, job_id: str, trigger_id: str) -> None:
        """Update next_run_at in the database from the scheduler job's next run time."""
        if not cls._scheduler:
            return
        job = cls._scheduler.get_job(job_id)
        if job and job.next_run_time:
            update_trigger_next_run(trigger_id, job.next_run_time.isoformat())
            logger.info(f"Scheduled trigger {trigger_id} - next run: {job.next_run_time}")

    @staticmethod
    def _job_to_dict(job) -> dict:
        """Convert an APScheduler job to a serializable dict."""
        return {
            "job_id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }

    @staticmethod
    def _parse_trigger_config(trigger_config) -> Optional[dict]:
        """Parse trigger_config from string or dict form. Returns None if empty."""
        if trigger_config and isinstance(trigger_config, str):
            try:
                trigger_config = json.loads(trigger_config)
            except (json.JSONDecodeError, TypeError):
                trigger_config = {}
        return trigger_config or None
