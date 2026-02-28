#!/usr/bin/env python3
"""Entry point for Agented backend API server."""

from dotenv import load_dotenv

load_dotenv()  # Load .env before anything else — override=False by default

import argparse
import atexit
import logging
import os
import signal
import sys

from app.logging_config import configure_logging

# Configure structured logging BEFORE app creation so all startup logs
# are formatted consistently.  Reads LOG_LEVEL and LOG_FORMAT env vars.
configure_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    log_format=os.environ.get("LOG_FORMAT", "json"),
)

# --- Sentry SDK initialization (must happen BEFORE create_app) ---
# When SENTRY_DSN is set, Sentry captures unhandled exceptions with full
# request context.  When unset (empty string or absent), this is a no-op
# and the server starts normally without a Sentry account.
import sentry_sdk  # noqa: E402

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:

    def _filter_sse_transactions(event, hint):
        """Drop Sentry transactions for long-lived SSE streaming endpoints.

        SSE endpoints keep connections open for minutes, creating extremely
        long-duration transactions that distort performance metrics and
        consume Sentry quota. See 05-RESEARCH.md Pitfall 5.
        """
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

from app import create_app  # noqa: E402

# Create application
application = create_app()


def _shutdown_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    import datetime

    from app.database import update_execution_status_cas
    from app.services.process_manager import ProcessManager

    print(f"\nReceived signal {signum}, initiating graceful shutdown...")
    active = ProcessManager.get_active_executions()
    if active:
        print(f"Waiting for {len(active)} active execution(s) to complete (max 300s)...")
    ProcessManager.cancel_all(timeout=300)

    # Mark any still-running executions as interrupted
    for eid in active:
        update_execution_status_cas(
            eid,
            new_status="interrupted",
            expected_status="running",
            finished_at=datetime.datetime.now().isoformat(),
            error_message="Server shutdown",
        )

    sys.exit(0)


def _atexit_cleanup():
    """Clean up any remaining processes on interpreter exit."""
    try:
        from app.services.process_manager import ProcessManager

        ProcessManager.cancel_all(timeout=10)
    except Exception:
        pass


# Only register in the main worker process (not the reloader parent in debug mode)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not any(
    "--debug" in a or "-d" in a for a in sys.argv[1:]
):
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)
    atexit.register(_atexit_cleanup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agented Backend API Server")
    parser.add_argument(
        "--port", "-p", type=int, default=20000, help="Port to run on (default: 20000)"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug mode (binds to localhost only)"
    )
    args = parser.parse_args()

    # In debug mode, only bind to localhost to prevent exposure
    host = "127.0.0.1" if args.debug else "0.0.0.0"
    if args.debug:
        print("WARNING: Debug mode enabled - binding to localhost only")

    application.run(host=host, port=args.port, debug=args.debug)
