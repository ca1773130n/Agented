"""Migrated to Litestar :20002 in wave 48 — see app_litestar/routes/misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="analytics", description="Migrated to Litestar")
cross_team_insights_bp = APIBlueprint("cross_team_insights", __name__, url_prefix="/admin", abp_tags=[tag])
