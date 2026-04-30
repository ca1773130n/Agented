"""Litestar app for Agented (track A migration foundation).

Runs alongside the Flask app on port 20002 during the migration period.
Routes opt-in to Litestar one at a time; once retired from Flask, the
frontend reaches them through `/litestar/*` (vite proxy in dev) or via
a unified gateway in prod (deferred).
"""

from .main import create_app

__all__ = ["create_app"]
