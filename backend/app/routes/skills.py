"""Migrated to Litestar :20002 in wave 57."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="skills", description="Migrated to Litestar")
skills_bp = APIBlueprint("skills_bp", __name__, url_prefix="/api/skills", abp_tags=[tag])
