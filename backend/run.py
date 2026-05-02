#!/usr/bin/env python3
"""Entry point for the Agented backend Litestar API server (wave 80).

Exposes `application` for gunicorn (`wsgi_app = "run:application"`) and
also runs standalone via `python run.py` for local dev convenience.

Sentry SDK and structured logging are initialised before app creation
so the on_startup scheduler/services share the same context.
"""

from dotenv import load_dotenv

load_dotenv()  # Load .env before anything else — override=False by default

import argparse
import logging
import os
import signal
import sys

from app.logging_config import configure_logging

configure_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    log_format=os.environ.get("LOG_FORMAT", "json"),
)

# --- Sentry SDK initialization (must happen BEFORE create_app) ---
import sentry_sdk  # noqa: E402

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:

    def _filter_sse_transactions(event, hint):  # noqa: ARG001
        tx = event.get("transaction", "")
        if "/stream" in tx or "/sessions/" in tx:
            return None
        return event

    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE", "agented@0.1.0"),
        send_default_pii=False,
        before_send_transaction=_filter_sse_transactions,
    )
    logging.getLogger(__name__).info("Sentry SDK initialized (environment=%s)", _sentry_dsn[:20])

from app_litestar.main import create_app  # noqa: E402

# Single Litestar instance reused by gunicorn workers + python run.py.
application = create_app()


def _shutdown_handler(signum, frame):  # noqa: ARG001
    """Graceful shutdown: cancel running CLI subprocesses, mark interrupted."""
    import datetime

    from app.database import update_execution_status_cas
    from app.services.process_manager import ProcessManager

    print(f"\nReceived signal {signum}, initiating graceful shutdown...")
    active = ProcessManager.get_active_executions()
    if active:
        print(f"Waiting for {len(active)} active execution(s) to complete (max 300s)...")
    ProcessManager.cancel_all(timeout=300)

    for eid in active:
        update_execution_status_cas(
            eid,
            new_status="interrupted",
            expected_status="running",
            finished_at=datetime.datetime.now().isoformat(),
            error_message="Server shutdown",
        )

    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Agented Backend API Server")
    parser.add_argument(
        "--port", "-p", type=int, default=20000, help="Port to run on (default: 20000)"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug mode (binds to localhost only)"
    )
    args = parser.parse_args()

    host = "127.0.0.1" if args.debug else "0.0.0.0"
    if args.debug:
        print("WARNING: Debug mode enabled — binding to localhost only")

    uvicorn.run(application, host=host, port=args.port, log_level="info")
