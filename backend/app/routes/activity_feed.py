"""Migrated to Litestar :20002 in wave 48 — see app_litestar/routes/misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="activity-feed", description="Migrated to Litestar")
activity_feed_bp = APIBlueprint("activity_feed", __name__, url_prefix="/api", abp_tags=[tag])
