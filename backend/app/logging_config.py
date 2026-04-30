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
import os
import re
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


_REDACT = "[REDACTED]"

# Order matters: match the most specific patterns first so we don't double-substitute.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer <token>
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), rf"\1{_REDACT}"),
    # X-API-Key / X-Api-Key headers (header-style, value runs to whitespace or end)
    (re.compile(r"(X-API-Key:\s*)[A-Za-z0-9._\-]+", re.IGNORECASE), rf"\1{_REDACT}"),
    # Anthropic / OpenAI key shapes — anywhere in the line.
    (re.compile(r"sk-(?:ant|proj|live|test)?-?[A-Za-z0-9_\-]{16,}"), _REDACT),
    # Query/form-style key=value pairs for known sensitive names.
    (
        re.compile(
            r"(token|password|api[_-]?key|secret)=[A-Za-z0-9._\-]+",
            re.IGNORECASE,
        ),
        lambda m: f"{m.group(1)}={_REDACT}",
    ),
)


class SensitiveDataFilter(logging.Filter):
    """Redact auth-shaped tokens from log record messages.

    Mutates ``record.msg`` and ``record.args`` so downstream formatters see
    redacted text. Always returns True (filter is purely transformative).

    CRITICAL: Must NEVER call any logging function — same recursion concern
    as :class:`RequestIdFilter`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._scrub(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._scrub(a) for a in record.args)
        return True

    @staticmethod
    def _scrub(value: object) -> object:
        if not isinstance(value, str):
            return value
        scrubbed = value
        for pattern, repl in _REDACTION_PATTERNS:
            scrubbed = pattern.sub(repl, scrubbed)
        return scrubbed


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
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "agented.log")

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

    # Attach filters to the HANDLER (not the root logger).
    # Filters on a logger only fire for events logged directly to that
    # logger; events propagated from child loggers skip parent-logger
    # filters but DO pass through parent-handler filters.
    # SensitiveDataFilter runs first so RequestIdFilter sees scrubbed args
    # if it ever inspects them (it currently doesn't, but keeps the
    # pipeline robust to future changes).
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(RequestIdFilter())

    root.addHandler(handler)

    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveDataFilter())
    file_handler.addFilter(RequestIdFilter())
    root.addHandler(file_handler)
