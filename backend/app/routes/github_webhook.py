"""Migrated to Litestar :20002 in wave 77 — see app_litestar/routes/webhooks.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="github-webhook", description="Migrated to Litestar")
github_webhook_bp = APIBlueprint(
    "github_webhook", __name__, url_prefix="/api/webhooks/github", abp_tags=[tag]
)
github_webhook_bp.strict_slashes = False
