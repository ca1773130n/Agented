"""Standalone Agented usage daemon.

Tracks token usage / cost and rate-limit windows for every account **in the
background, continuously, independent of the web UI or the main backend
process**. This is the answer to "track usage regardless of user activity":
the web backend's in-process APScheduler only runs while gunicorn is up and
exists mainly to serve the console, whereas this daemon does nothing but the
tracking and is meant to run 24/7 under launchd / systemd.

It runs two jobs on independent cadences, writing to the SAME ``agented.db``:

  * ``SessionCollectionService.collect_all`` — parses local Claude/Codex
    session transcripts into the ``token_usage`` table (the Cost dashboard).
    Default every ``AGENTED_USAGE_COLLECT_MINUTES`` (10) minutes.
  * ``MonitoringService._poll_usage`` — polls each enabled account's provider
    for rate-limit windows into ``rate_limit_snapshots`` (the gauges).
    Honors ``monitoring_config.polling_minutes`` and the enabled flag.

Run it standalone:

    cd backend && uv run python scripts/run_usage_daemon.py

…or 24/7 via launchd (macOS):

    just usage-daemon-install      # copies + loads the LaunchAgent

When this daemon owns tracking, set ``AGENTED_EXTERNAL_USAGE_DAEMON=1`` in the
web backend's environment so it does NOT also register the same two jobs
(prevents double collection / SQLite write contention).
"""

from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s usage-daemon %(message)s",
)
logger = logging.getLogger("agented.usage_daemon")

_running = True


def _stop(signum, _frame) -> None:
    global _running
    logger.info("received signal %s — shutting down after current cycle", signum)
    _running = False


def main() -> None:
    from app.database import get_monitoring_config, init_db
    from app.services.monitoring_service import MonitoringService
    from app.services.session_collection_service import SessionCollectionService

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    init_db()  # ensure schema + migrations are applied for this process

    collect_every = max(60, int(os.environ.get("AGENTED_USAGE_COLLECT_MINUTES", "10")) * 60)
    next_collect = 0.0
    next_poll = 0.0
    logger.info("started — collect every %ds; poll on monitoring_config interval", collect_every)

    while _running:
        now = time.monotonic()

        if now >= next_collect:
            try:
                res = SessionCollectionService.collect_all()
                logger.info("collect_all: %s", res)
            except Exception:  # noqa: BLE001
                logger.warning("collect_all failed", exc_info=True)
            next_collect = time.monotonic() + collect_every

        if now >= next_poll:
            poll_minutes = 30
            try:
                cfg = get_monitoring_config()
                poll_minutes = max(1, int(cfg.get("polling_minutes", 30)))
                if cfg.get("enabled"):
                    MonitoringService._poll_usage()
                    logger.info("poll_usage done (next in %dm)", poll_minutes)
                else:
                    logger.info("monitoring disabled — skipping poll")
            except Exception:  # noqa: BLE001
                logger.warning("poll_usage failed", exc_info=True)
            next_poll = time.monotonic() + poll_minutes * 60

        # Short sleep so SIGTERM is honored promptly between cadence checks.
        time.sleep(5)

    logger.info("stopped")


if __name__ == "__main__":
    main()
