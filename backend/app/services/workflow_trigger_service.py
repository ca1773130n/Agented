"""Workflow trigger service — manages four expanded trigger types for workflows:
completion triggers (workflow chaining), cron triggers, API polling triggers,
and file system watch triggers."""

import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _WorkflowFileWatchHandler:
    """File system event handler with debouncing for workflow file watch triggers.

    Follows the PluginFileWatcher pattern: accumulates events in a pending dict
    and processes them after a debounce window expires.
    """

    DEBOUNCE_SECONDS = 1.0

    def __init__(self, workflow_id: str, patterns: Optional[List[str]] = None):
        self.workflow_id = workflow_id
        self.patterns = patterns
        self._pending: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def dispatch(self, event):
        """Dispatch incoming watchdog event with pattern matching and debounce."""
        if event.is_directory:
            return

        src_path = event.src_path
        event_type = event.event_type

        # Pattern filtering: if patterns specified, match against file name
        if self.patterns:
            import fnmatch
            import os

            filename = os.path.basename(src_path)
            if not any(fnmatch.fnmatch(filename, pat) for pat in self.patterns):
                return

        with self._lock:
            self._pending[src_path] = time.time()
            self._last_event_type = event_type

        self._schedule_process()

    def _schedule_process(self):
        """Cancel existing timer and schedule a new debounced processing run."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.DEBOUNCE_SECONDS, self._process_pending)
        self._timer.daemon = True
        self._timer.start()

    def _process_pending(self):
        """Process all pending file changes after debounce window."""
        with self._lock:
            paths = dict(self._pending)
            self._pending.clear()
            event_type = getattr(self, "_last_event_type", "modified")

        if not paths:
            return

        try:
            from .workflow_execution_service import WorkflowExecutionService

            for src_path in paths:
                input_data = json.dumps({"event_type": event_type, "src_path": src_path})
                WorkflowExecutionService.execute_workflow(
                    self.workflow_id,
                    input_json=input_data,
                    trigger_type="file_watch",
                )
                logger.info(
                    f"File watch trigger fired workflow {self.workflow_id} " f"for path {src_path}"
                )
        except Exception as e:
            logger.error(f"Error firing file watch trigger for workflow {self.workflow_id}: {e}")

    def stop(self):
        """Cancel any pending timer."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class WorkflowTriggerService:
    """Service managing four expanded trigger types for workflows.

    Trigger types:
    1. Completion — fires target workflow when source entity finishes execution
    2. Cron — fires workflow on a cron schedule via APScheduler
    3. Polling — polls an HTTP endpoint and fires workflow when response changes
    4. File watch — monitors filesystem paths and fires workflow on file changes

    All trigger configurations are persisted in the workflow's trigger_config
    column and reloaded on startup.
    """

    # {(entity_type, entity_id): [workflow_id, ...]}
    _completion_callbacks: Dict[tuple, List[str]] = {}
    # {workflow_id: {"last_hash": str|None, "job_id": str, "url": str}}
    _polling_jobs: Dict[str, dict] = {}
    # {workflow_id: {"observer": Observer, "handler": _WorkflowFileWatchHandler}}
    _file_watchers: Dict[str, Any] = {}
    _lock = threading.Lock()
    _initialized: bool = False

    MAX_CHAIN_DEPTH = 10

    # =========================================================================
    # Initialization and Shutdown
    # =========================================================================

    @classmethod
    def init(cls):
        """Initialize trigger service — load all trigger configs from DB.

        Called from SchedulerService.init() after scheduler is started.
        """
        if cls._initialized:
            return

        cls._initialized = True

        try:
            cls._load_completion_triggers()
            cls._load_cron_triggers()
            cls._load_polling_triggers()
            cls._load_file_watch_triggers()
        except Exception as e:
            logger.error(f"Error initializing workflow triggers: {e}")

    @classmethod
    def shutdown(cls):
        """Stop all file watchers. Cron/polling jobs stopped by SchedulerService."""
        with cls._lock:
            for wf_id, watcher_info in list(cls._file_watchers.items()):
                try:
                    observer = watcher_info.get("observer")
                    handler = watcher_info.get("handler")
                    if observer:
                        observer.stop()
                        observer.join(timeout=5)
                    if handler:
                        handler.stop()
                except Exception as e:
                    logger.error(f"Error stopping file watcher for workflow {wf_id}: {e}")
            cls._file_watchers.clear()
            cls._initialized = False
        logger.info("Workflow trigger service shutdown")

    @classmethod
    def reset(cls):
        """Reset all in-memory state. Used for testing."""
        with cls._lock:
            cls._completion_callbacks.clear()
            cls._polling_jobs.clear()
            # Stop file watchers
            for wf_id, watcher_info in list(cls._file_watchers.items()):
                try:
                    observer = watcher_info.get("observer")
                    handler = watcher_info.get("handler")
                    if observer:
                        observer.stop()
                        observer.join(timeout=2)
                    if handler:
                        handler.stop()
                except Exception as e:
                    logger.debug("Trigger lifecycle: %s", e)
            cls._file_watchers.clear()
            cls._initialized = False

    # =========================================================================
    # 1. Completion Triggers (workflow/agent chaining)
    # =========================================================================

    @classmethod
    def register_completion_trigger(cls, source_type: str, source_id: str, target_workflow_id: str):
        """Register a callback: when (source_type, source_id) completes, fire target workflow.

        Args:
            source_type: Entity type — "workflow", "agent", or "team".
            source_id: Entity ID of the source.
            target_workflow_id: Workflow ID to fire on source completion.
        """
        key = (source_type, source_id)
        with cls._lock:
            if key not in cls._completion_callbacks:
                cls._completion_callbacks[key] = []
            if target_workflow_id not in cls._completion_callbacks[key]:
                cls._completion_callbacks[key].append(target_workflow_id)
        logger.info(
            f"Registered completion trigger: {source_type}/{source_id} -> {target_workflow_id}"
        )

    @classmethod
    def unregister_completion_trigger(
        cls, source_type: str, source_id: str, target_workflow_id: str
    ):
        """Remove a specific completion callback registration."""
        key = (source_type, source_id)
        with cls._lock:
            if key in cls._completion_callbacks:
                callbacks = cls._completion_callbacks[key]
                if target_workflow_id in callbacks:
                    callbacks.remove(target_workflow_id)
                if not callbacks:
                    del cls._completion_callbacks[key]
        logger.info(
            f"Unregistered completion trigger: {source_type}/{source_id} -> {target_workflow_id}"
        )

    @classmethod
    def on_execution_complete(
        cls,
        entity_type: str,
        entity_id: str,
        status: str,
        output: dict = None,
        chain_depth: int = 0,
    ):
        """Called when any execution completes. Fires registered completion triggers.

        Args:
            entity_type: Type of the completed entity ("workflow", "agent", "team").
            entity_id: ID of the completed entity.
            status: Final status of the execution.
            output: Optional output data from the execution.
            chain_depth: Current chain depth for recursion protection.
        """
        key = (entity_type, entity_id)
        with cls._lock:
            targets = list(cls._completion_callbacks.get(key, []))

        if not targets:
            return

        for wf_id in targets:
            if chain_depth >= cls.MAX_CHAIN_DEPTH:
                logger.warning(
                    f"Max chain depth reached ({cls.MAX_CHAIN_DEPTH}), "
                    f"refusing to fire workflow {wf_id}"
                )
                continue

            try:
                from .workflow_execution_service import WorkflowExecutionService

                input_data = json.dumps(
                    {
                        "source_type": entity_type,
                        "source_id": entity_id,
                        "status": status,
                        "output": output,
                        "chain_depth": chain_depth + 1,
                    }
                )
                WorkflowExecutionService.execute_workflow(
                    wf_id,
                    input_json=input_data,
                    trigger_type="completion",
                )
                logger.info(
                    f"Completion trigger fired workflow {wf_id} "
                    f"(source={entity_type}/{entity_id}, depth={chain_depth + 1})"
                )
            except Exception as e:
                logger.error(f"Error firing completion trigger for workflow {wf_id}: {e}")

    @classmethod
    def _load_completion_triggers(cls):
        """Load completion triggers from DB on startup."""
        try:
            from ..db.workflows import get_all_workflows

            workflows = get_all_workflows()
            count = 0
            for wf in workflows:
                if wf.get("trigger_type") == "completion" and wf.get("enabled", 1):
                    config_str = wf.get("trigger_config")
                    if not config_str:
                        continue
                    try:
                        config = json.loads(config_str)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    source_type = config.get("source_type")
                    source_id = config.get("source_id")
                    if source_type and source_id:
                        cls.register_completion_trigger(source_type, source_id, wf["id"])
                        count += 1
            logger.info(f"Loaded {count} completion triggers from DB")
        except Exception as e:
            logger.error(f"Error loading completion triggers: {e}")

    # =========================================================================
    # 2. Full Cron Expression Support
    # =========================================================================

    @classmethod
    def register_cron_trigger(
        cls, workflow_id: str, cron_expression: str, timezone_str: str = "UTC"
    ):
        """Register a cron-based workflow trigger using APScheduler.

        Uses CronTrigger.from_crontab() for full cron expression support.

        Args:
            workflow_id: Workflow to fire on schedule.
            cron_expression: Standard cron expression (5 fields).
            timezone_str: Timezone name (e.g., "UTC", "America/New_York").

        Raises:
            ValueError: If cron expression is invalid or scheduler not available.
        """
        from .scheduler_service import SCHEDULER_AVAILABLE, SchedulerService

        if not SCHEDULER_AVAILABLE:
            raise ValueError("APScheduler not available — cannot register cron trigger")

        if not SchedulerService._scheduler:
            raise ValueError("Scheduler not initialized — cannot register cron trigger")

        # Import CronTrigger and pytz from scheduler_service's cached imports
        # (these are conditionally imported at module level in scheduler_service)
        from . import scheduler_service as sched_mod

        CronTrigger = sched_mod.CronTrigger
        pytz = sched_mod.pytz

        job_id = f"wf-cron-{workflow_id}"

        # Remove existing job if any
        existing = SchedulerService._scheduler.get_job(job_id)
        if existing:
            SchedulerService._scheduler.remove_job(job_id)

        try:
            tz = pytz.timezone(timezone_str)
        except Exception as e:
            logger.debug("Timezone parse fallback to UTC: %s", e)
            tz = pytz.UTC

        try:
            cron_trigger = CronTrigger.from_crontab(cron_expression, timezone=tz)
        except ValueError as e:
            raise ValueError(f"Invalid cron expression '{cron_expression}': {e}")

        SchedulerService._scheduler.add_job(
            cls._fire_cron_workflow,
            trigger=cron_trigger,
            id=job_id,
            args=[workflow_id],
            replace_existing=True,
            name=f"Workflow cron: {workflow_id}",
        )
        logger.info(
            f"Registered cron trigger for workflow {workflow_id}: "
            f"{cron_expression} ({timezone_str})"
        )

    @classmethod
    def unregister_cron_trigger(cls, workflow_id: str):
        """Remove a cron trigger from the scheduler."""
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            return

        job_id = f"wf-cron-{workflow_id}"
        existing = SchedulerService._scheduler.get_job(job_id)
        if existing:
            SchedulerService._scheduler.remove_job(job_id)
            logger.info(f"Unregistered cron trigger for workflow {workflow_id}")

    @classmethod
    def _fire_cron_workflow(cls, workflow_id: str):
        """Execute a cron-triggered workflow. Called by APScheduler."""
        try:
            from .workflow_execution_service import WorkflowExecutionService

            WorkflowExecutionService.execute_workflow(workflow_id, trigger_type="cron")
            logger.info(f"Cron trigger fired workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Error firing cron workflow {workflow_id}: {e}")

    @classmethod
    def _load_cron_triggers(cls):
        """Load cron triggers from DB on startup."""
        try:
            from ..db.workflows import get_all_workflows

            workflows = get_all_workflows()
            count = 0
            for wf in workflows:
                if wf.get("trigger_type") == "cron" and wf.get("enabled", 1):
                    config_str = wf.get("trigger_config")
                    if not config_str:
                        continue
                    try:
                        config = json.loads(config_str)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    cron_expr = config.get("cron_expression")
                    tz = config.get("timezone", "UTC")
                    if cron_expr:
                        try:
                            cls.register_cron_trigger(wf["id"], cron_expr, tz)
                            count += 1
                        except ValueError as e:
                            logger.warning(
                                f"Skipping invalid cron trigger for workflow {wf['id']}: {e}"
                            )
            logger.info(f"Loaded {count} cron triggers from DB")
        except Exception as e:
            logger.error(f"Error loading cron triggers: {e}")

    # =========================================================================
    # 3. API Polling Trigger
    # =========================================================================

    @classmethod
    def register_polling_trigger(
        cls,
        workflow_id: str,
        url: str,
        interval_seconds: int = 60,
        method: str = "GET",
        headers: dict = None,
        condition: str = "status_changed",
    ):
        """Register an API polling trigger that fires workflow when response changes.

        Args:
            workflow_id: Workflow to fire when condition met.
            url: URL to poll.
            interval_seconds: Polling interval in seconds.
            method: HTTP method (GET or POST).
            headers: Optional HTTP headers dict.
            condition: Trigger condition — "status_changed" or "always".
        """
        from .scheduler_service import SCHEDULER_AVAILABLE, SchedulerService

        if not SCHEDULER_AVAILABLE:
            raise ValueError("APScheduler not available — cannot register polling trigger")

        if not SchedulerService._scheduler:
            raise ValueError("Scheduler not initialized — cannot register polling trigger")

        job_id = f"wf-poll-{workflow_id}"

        # Remove existing job if any
        existing = SchedulerService._scheduler.get_job(job_id)
        if existing:
            SchedulerService._scheduler.remove_job(job_id)

        # Store polling state
        with cls._lock:
            cls._polling_jobs[workflow_id] = {
                "last_hash": None,
                "job_id": job_id,
                "url": url,
                "method": method,
                "headers": headers,
                "condition": condition,
            }

        SchedulerService._scheduler.add_job(
            cls._poll_api,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id,
            args=[workflow_id, url, method, headers, condition],
            replace_existing=True,
            name=f"Workflow poll: {workflow_id}",
        )
        logger.info(
            f"Registered polling trigger for workflow {workflow_id}: "
            f"{method} {url} every {interval_seconds}s"
        )

    @classmethod
    def _poll_api(
        cls,
        workflow_id: str,
        url: str,
        method: str,
        headers: dict,
        condition: str,
    ):
        """Poll an API endpoint and fire workflow if response changed.

        Uses SHA-256 hash comparison for deduplication.
        """
        try:
            req = urllib.request.Request(url, method=method)
            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)

            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Polling request failed for workflow {workflow_id}: {e}")
            return

        # Compute hash of response body
        current_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        with cls._lock:
            poll_state = cls._polling_jobs.get(workflow_id, {})
            last_hash = poll_state.get("last_hash")

        # Determine if we should fire
        should_fire = False
        if condition == "always":
            should_fire = True
        elif last_hash is None:
            # First poll: fire if condition is "always", otherwise just record hash
            if condition == "always":
                should_fire = True
            else:
                # Record initial hash, don't fire on first poll
                with cls._lock:
                    if workflow_id in cls._polling_jobs:
                        cls._polling_jobs[workflow_id]["last_hash"] = current_hash
                return
        elif current_hash != last_hash:
            should_fire = True

        # Update stored hash
        with cls._lock:
            if workflow_id in cls._polling_jobs:
                cls._polling_jobs[workflow_id]["last_hash"] = current_hash

        if should_fire:
            try:
                from .workflow_execution_service import WorkflowExecutionService

                input_data = json.dumps(
                    {
                        "poll_url": url,
                        "response_body": body[:5000],
                    }
                )
                WorkflowExecutionService.execute_workflow(
                    workflow_id,
                    input_json=input_data,
                    trigger_type="poll",
                )
                logger.info(f"Polling trigger fired workflow {workflow_id}")
            except Exception as e:
                logger.error(f"Error firing polling trigger for workflow {workflow_id}: {e}")

    @classmethod
    def unregister_polling_trigger(cls, workflow_id: str):
        """Remove a polling trigger from the scheduler."""
        from .scheduler_service import SchedulerService

        if SchedulerService._scheduler:
            job_id = f"wf-poll-{workflow_id}"
            existing = SchedulerService._scheduler.get_job(job_id)
            if existing:
                SchedulerService._scheduler.remove_job(job_id)

        with cls._lock:
            cls._polling_jobs.pop(workflow_id, None)

        logger.info(f"Unregistered polling trigger for workflow {workflow_id}")

    @classmethod
    def _load_polling_triggers(cls):
        """Load polling triggers from DB on startup."""
        try:
            from ..db.workflows import get_all_workflows

            workflows = get_all_workflows()
            count = 0
            for wf in workflows:
                if wf.get("trigger_type") == "poll" and wf.get("enabled", 1):
                    config_str = wf.get("trigger_config")
                    if not config_str:
                        continue
                    try:
                        config = json.loads(config_str)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    url = config.get("url")
                    if url:
                        try:
                            cls.register_polling_trigger(
                                workflow_id=wf["id"],
                                url=url,
                                interval_seconds=config.get("interval_seconds", 60),
                                method=config.get("method", "GET"),
                                headers=config.get("headers"),
                                condition=config.get("condition", "status_changed"),
                            )
                            count += 1
                        except ValueError as e:
                            logger.warning(f"Skipping polling trigger for workflow {wf['id']}: {e}")
            logger.info(f"Loaded {count} polling triggers from DB")
        except Exception as e:
            logger.error(f"Error loading polling triggers: {e}")

    # =========================================================================
    # 4. File System Watch Trigger
    # =========================================================================

    @classmethod
    def register_file_watch_trigger(
        cls,
        workflow_id: str,
        watch_path: str,
        patterns: Optional[List[str]] = None,
        recursive: bool = True,
    ):
        """Register a file system watch trigger using watchdog.

        Follows the PluginFileWatcher pattern with debouncing.

        Args:
            workflow_id: Workflow to fire on file changes.
            watch_path: Directory path to watch.
            patterns: Optional list of glob patterns for file matching (e.g., ["*.py", "*.json"]).
            recursive: Whether to watch subdirectories.
        """
        import os

        from watchdog.observers import Observer

        if not os.path.isdir(watch_path):
            raise ValueError(f"Watch path is not a directory: {watch_path}")

        # Stop existing watcher if any
        cls.unregister_file_watch_trigger(workflow_id)

        handler = _WorkflowFileWatchHandler(workflow_id, patterns=patterns)
        observer = Observer()
        observer.schedule(handler, watch_path, recursive=recursive)
        observer.daemon = True
        observer.start()

        with cls._lock:
            cls._file_watchers[workflow_id] = {
                "observer": observer,
                "handler": handler,
                "watch_path": watch_path,
            }

        logger.info(
            f"Registered file watch trigger for workflow {workflow_id}: "
            f"{watch_path} (patterns={patterns}, recursive={recursive})"
        )

    @classmethod
    def unregister_file_watch_trigger(cls, workflow_id: str):
        """Stop and remove a file watch trigger."""
        with cls._lock:
            watcher_info = cls._file_watchers.pop(workflow_id, None)

        if watcher_info:
            observer = watcher_info.get("observer")
            handler = watcher_info.get("handler")
            if observer:
                observer.stop()
                observer.join(timeout=5)
            if handler:
                handler.stop()
            logger.info(f"Unregistered file watch trigger for workflow {workflow_id}")

    @classmethod
    def _load_file_watch_triggers(cls):
        """Load file watch triggers from DB on startup."""
        try:
            from ..db.workflows import get_all_workflows

            workflows = get_all_workflows()
            count = 0
            for wf in workflows:
                if wf.get("trigger_type") == "file_watch" and wf.get("enabled", 1):
                    config_str = wf.get("trigger_config")
                    if not config_str:
                        continue
                    try:
                        config = json.loads(config_str)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    watch_path = config.get("watch_path")
                    if watch_path:
                        try:
                            cls.register_file_watch_trigger(
                                workflow_id=wf["id"],
                                watch_path=watch_path,
                                patterns=config.get("patterns"),
                                recursive=config.get("recursive", True),
                            )
                            count += 1
                        except ValueError as e:
                            logger.warning(
                                f"Skipping file watch trigger for workflow {wf['id']}: {e}"
                            )
            logger.info(f"Loaded {count} file watch triggers from DB")
        except Exception as e:
            logger.error(f"Error loading file watch triggers: {e}")

    # =========================================================================
    # Trigger Registration (generic)
    # =========================================================================

    @classmethod
    def register_trigger(cls, workflow_id: str, trigger_type: str, trigger_config: dict):
        """Register a trigger based on type and config.

        Called by the trigger management API endpoint.

        Args:
            workflow_id: Workflow to register trigger for.
            trigger_type: One of "completion", "cron", "poll", "file_watch".
            trigger_config: Configuration dict for the trigger type.

        Raises:
            ValueError: If trigger_type is unknown or config is invalid.
        """
        if trigger_type == "completion":
            source_type = trigger_config.get("source_type")
            source_id = trigger_config.get("source_id")
            if not source_type or not source_id:
                raise ValueError("Completion trigger requires source_type and source_id")
            cls.register_completion_trigger(source_type, source_id, workflow_id)

        elif trigger_type == "cron":
            cron_expression = trigger_config.get("cron_expression")
            if not cron_expression:
                raise ValueError("Cron trigger requires cron_expression")
            timezone_str = trigger_config.get("timezone", "UTC")
            cls.register_cron_trigger(workflow_id, cron_expression, timezone_str)

        elif trigger_type == "poll":
            url = trigger_config.get("url")
            if not url:
                raise ValueError("Polling trigger requires url")
            cls.register_polling_trigger(
                workflow_id=workflow_id,
                url=url,
                interval_seconds=trigger_config.get("interval_seconds", 60),
                method=trigger_config.get("method", "GET"),
                headers=trigger_config.get("headers"),
                condition=trigger_config.get("condition", "status_changed"),
            )

        elif trigger_type == "file_watch":
            watch_path = trigger_config.get("watch_path")
            if not watch_path:
                raise ValueError("File watch trigger requires watch_path")
            cls.register_file_watch_trigger(
                workflow_id=workflow_id,
                watch_path=watch_path,
                patterns=trigger_config.get("patterns"),
                recursive=trigger_config.get("recursive", True),
            )

        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")

    @classmethod
    def unregister_trigger(cls, workflow_id: str, trigger_type: str):
        """Unregister a trigger based on type.

        Args:
            workflow_id: Workflow to unregister trigger for.
            trigger_type: One of "completion", "cron", "poll", "file_watch".
        """
        if trigger_type == "completion":
            # Need to find and remove all completion callbacks for this workflow
            with cls._lock:
                keys_to_clean = []
                for key, targets in cls._completion_callbacks.items():
                    if workflow_id in targets:
                        keys_to_clean.append(key)

            for key in keys_to_clean:
                cls.unregister_completion_trigger(key[0], key[1], workflow_id)

        elif trigger_type == "cron":
            cls.unregister_cron_trigger(workflow_id)

        elif trigger_type == "poll":
            cls.unregister_polling_trigger(workflow_id)

        elif trigger_type == "file_watch":
            cls.unregister_file_watch_trigger(workflow_id)

        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
