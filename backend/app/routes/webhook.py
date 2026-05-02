"""Migrated to Litestar :20002 in wave 77 — see app_litestar/routes/webhooks.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="webhook", description="Migrated to Litestar")
webhook_bp = APIBlueprint("webhook", __name__, abp_tags=[tag])
