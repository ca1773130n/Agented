"""Gunicorn configuration for Agented backend.

workers=1 is MANDATORY until in-memory SSE state is migrated to Redis.
The following services store state in class-level dicts or module globals
that are NOT shared across processes:
- ExecutionLogService._subscribers (SSE event delivery)
- ProcessManager._processes (subprocess lifecycle tracking)
- AgentMessageBusService._subscribers (agent SSE streams)
- SchedulerService._scheduler (APScheduler job registry)
- MonitoringService session tracking
- Rate-limit retry state in ExecutionService

With workers>1, each worker has independent copies of this state, causing
SSE subscriptions to miss events and rate-limit detection to be invisible
across workers. See .planning/codebase/CONCERNS.md Section 7.2.
"""

from dotenv import load_dotenv

load_dotenv()

import os

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:20000")

# Worker processes — see module docstring for why this MUST be 1
workers = 1

# Gevent worker class for async SSE support.
# Allows the single worker to handle many concurrent long-lived SSE
# connections via cooperative greenlet scheduling.
# Gunicorn's GeventWorker calls monkey.patch_all() before loading the app,
# which transparently converts threading.Thread/Lock to greenlets and
# subprocess.Popen to a cooperative version.
worker_class = "gevent"

# Max concurrent greenlets per worker
worker_connections = 1000

# Timeout for worker response (seconds).
# Long timeout to accommodate SSE streams and long-running AI executions
# (Claude CLI subprocess can run for several minutes).
timeout = 300

# Graceful timeout — time to finish in-flight requests after SIGTERM
graceful_timeout = 30

# Do NOT set preload_app = True. With gevent workers, monkey patching
# happens post-fork in GeventWorker.patch(). preload_app loads the app
# in the master process BEFORE monkey patching, causing unpatched module
# references. See 02-RESEARCH.md Pitfall 3.

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("LOG_LEVEL", "info")

# WSGI application — references the `application` object in run.py
wsgi_app = "run:application"
