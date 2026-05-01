"""Migrated to Litestar :20002 in wave 53 — see app_litestar/routes/teams.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="team_edges", description="Migrated to Litestar")
team_edges_bp = APIBlueprint("team_edges_bp", __name__, url_prefix="/admin/teams", abp_tags=[tag])
