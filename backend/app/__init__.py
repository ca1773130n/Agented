"""Backwards-compat shim — retired in wave 80.

The Flask application factory has been replaced by `app_litestar.main.create_app`.
This module survives only so legacy tests that do `from app import create_app`
keep importing without ImportError. The returned object is an empty Flask app
with no routes, middleware, or background services — those all live on Litestar
now (see `app_litestar/`). Tests that exercised real routes via the Flask test
client should be migrated to `litestar.testing.create_test_client` against the
relevant router from `app_litestar.routes.*`.

Service modules (`app/services/*`, `app/db/*`, `app/database.py`,
`app/config.py`, `app/logging_config.py`, `app/models/*`) remain in place
because they're imported directly by the Litestar handlers.
"""

from __future__ import annotations

from flask import Flask

# Accumulated non-fatal startup warnings, exposed via /health/readiness.
# Kept for backwards compatibility with code that does `from app import _startup_warnings`.
_startup_warnings: list[str] = []


def create_app(config: dict | None = None):  # noqa: ARG001 — kept for compat
    """Return a route-less Flask app. Real surface lives on Litestar."""
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    if config:
        app.config.from_mapping(config)
    return app
