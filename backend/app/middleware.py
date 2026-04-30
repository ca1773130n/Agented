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

from .db.rbac import get_role_and_user_for_api_key
from .logging_config import current_user_var, request_id_var

_request_logger = logging.getLogger("app.request")


def init_request_middleware(app):
    """Register before/after/teardown hooks on *app* for request ID lifecycle."""

    @app.before_request
    def set_request_context():
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(rid)
        g.request_id = rid

        # Resolve the authenticated user from the API key (track B, wave 21).
        # Background tasks and unauthenticated bootstrap routes leave
        # current_user_var as None.
        user_id: str | None = None
        api_key = request.headers.get("X-API-Key")
        if api_key:
            try:
                resolved = get_role_and_user_for_api_key(api_key)
                if resolved is not None:
                    _, user_id = resolved
            except Exception as exc:  # noqa: BLE001
                _request_logger.debug("user lookup failed: %s", exc)
        current_user_var.set(user_id)
        g.current_user_id = user_id

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
    def clear_request_context(exc):  # noqa: ARG001
        # Defense-in-depth: prevent context leakage across greenlets
        # (see 05-RESEARCH.md Pitfall 1).
        request_id_var.set(None)
        current_user_var.set(None)
