"""Migrated to Litestar :20002 (waves 76 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="team-generation", description="Migrated to Litestar")
team_generation_bp = APIBlueprint(
    "team_generation", __name__, url_prefix="/admin/teams", abp_tags=[tag]
)
