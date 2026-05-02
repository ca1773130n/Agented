"""Migrated to Litestar :20002 in wave 57."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="skill_sets", description="Migrated to Litestar")
skill_sets_bp = APIBlueprint("skill_sets_bp", __name__, url_prefix="/api/skill-sets", abp_tags=[tag])
