"""Gunicorn configuration for Agented backend.

Serves the Litestar ASGI app (`app_litestar.main:create_app()`) via the
UvicornWorker worker class. Wave 80 retires the Flask app — every route,
middleware, scheduler and lifecycle hook now lives on Litestar. Process
management still goes through gunicorn so existing scripts (`just deploy`,
launchd, systemd units, ...) keep working without changes.

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
import resource
import sys


def on_starting(server):
    """v0.5.13: validate required env vars before workers spawn.

    In dev (AGENTED_ENV unset or != 'production'), warnings only.
    In production, missing required vars cause an immediate exit
    rather than a silently-degraded boot."""
    from scripts.check_env import main as _check_env
    rc = _check_env([])
    if rc != 0:
        server.log.error("env-var validation failed; refusing to start")
        sys.exit(rc)

# Bump soft file-descriptor limit early. macOS defaults to 256, which the
# bundle plugin install + concurrent SQLite connections can blow past,
# surfacing as "Too many open files" + "unable to open database file"
# during plugin extraction.
try:
    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if _soft < 8192:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(8192, _hard), _hard))
except (ValueError, OSError):
    pass

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:20000")

# Single worker — see module docstring for why this MUST be 1.
workers = 1

# UvicornWorker drives the Litestar ASGI app. Async SSE / long-lived
# streams are handled by uvicorn's event loop (asyncio + httptools).
worker_class = "uvicorn.workers.UvicornWorker"

# Generous timeout so Claude/Codex CLI subprocesses (multi-minute) and
# SSE streams don't trip Gunicorn's worker-stuck detector.
timeout = 300

# Graceful timeout — time to finish in-flight requests after SIGTERM
graceful_timeout = 30

# Logging
accesslog = None
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# ASGI application — references the `application` callable in run.py
wsgi_app = "run:application"
