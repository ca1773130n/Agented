#!/usr/bin/env python3
"""Entry point for Hive backend API server."""

import argparse
import atexit
import logging
import os
import signal
import sys

# Configure root logger so all app.* loggers output to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app import create_app

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
    parser = argparse.ArgumentParser(description="Hive Backend API Server")
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
