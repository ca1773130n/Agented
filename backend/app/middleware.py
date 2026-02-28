"""Request ID middleware for Flask.

Generates a UUID-v4 request ID for every incoming HTTP request, stores it in
a :class:`~contextvars.ContextVar` for the structured logging filter, and
returns it to the client via the ``X-Request-ID`` response header.

If the incoming request already carries an ``X-Request-ID`` header (e.g. from
an upstream load-balancer or API gateway), that value is honoured instead of
generating a new one.

Usage — call once inside the app factory::

    from .middleware import init_request_middleware
    init_request_middleware(app)

Corresponds to 05-RESEARCH.md Recommendation 2 (contextvars pattern).
"""

import logging
import uuid

from flask import g, request

from .logging_config import request_id_var

_request_logger = logging.getLogger("app.request")


def init_request_middleware(app):
    """Register before/after/teardown hooks on *app* for request ID lifecycle."""

    @app.before_request
    def set_request_id():
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(rid)
        g.request_id = rid

    @app.after_request
    def log_request(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "unknown")
        _request_logger.info(
            "%s %s %s %s",
            request.method,
            request.path,
            response.status_code,
            response.content_length,
        )
        return response

    @app.teardown_request
    def clear_request_id(exc):  # noqa: ARG001
        # Defense-in-depth: prevent context leakage across greenlets
        # (see 05-RESEARCH.md Pitfall 1).
        request_id_var.set(None)
