"""Structured JSON logging configuration with request ID correlation.

Provides:
- ``request_id_var``: :class:`~contextvars.ContextVar` holding the current
  request's UUID (or ``None`` outside a request context).
- ``RequestIdFilter``: :class:`logging.Filter` that injects ``request_id``
  into every log record.
- ``configure_logging()``: Configures the root logger with either JSON
  (default) or plaintext output.

Usage::

    from app.logging_config import configure_logging
    configure_logging(log_level="INFO", log_format="json")

Corresponds to 05-RESEARCH.md Recommendations 1-2.
"""

import logging
import sys
from contextvars import ContextVar

# Single source of truth for the current request's ID.
# Set by middleware (before_request), cleared on teardown.
# Background tasks (APScheduler) leave this as None.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Inject ``request_id`` from the context variable into every log record.

    CRITICAL: This filter must NEVER call any logging function.
    Doing so would cause infinite recursion because this filter is
    attached to the root logger.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        return True


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure the root logger with JSON or plaintext output.

    Parameters
    ----------
    log_level:
        Standard Python log level name (e.g. ``"INFO"``, ``"DEBUG"``).
    log_format:
        ``"json"`` for machine-parseable JSON lines (default), anything
        else for human-readable plaintext.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level.upper())

    handler = logging.StreamHandler(sys.stderr)

    if log_format == "json":
        from pythonjsonlogger.json import JsonFormatter  # v3 import path

        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)

    # Attach RequestIdFilter to the HANDLER (not the root logger).
    # Filters on a logger only fire for events logged directly to that
    # logger; events propagated from child loggers skip parent-logger
    # filters but DO pass through parent-handler filters.
    handler.addFilter(RequestIdFilter())

    root.addHandler(handler)
