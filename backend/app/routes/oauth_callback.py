"""Migrated to Litestar :20002 in wave 77 — see app_litestar/routes/webhooks.py."""

from flask_openapi3 import APIBlueprint

oauth_callback_bp = APIBlueprint(
    "oauth_callback", __name__, url_prefix="/api/oauth-callback"
)
