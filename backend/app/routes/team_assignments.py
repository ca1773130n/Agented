"""Migrated to Litestar :20002 in wave 53 — see app_litestar/routes/teams.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="team_assignments", description="Migrated to Litestar")
team_assignments_bp = APIBlueprint("team_assignments_bp", __name__, url_prefix="/admin/teams", abp_tags=[tag])
