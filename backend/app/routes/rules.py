"""Migrated to Litestar :20002 in wave 61."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="rules", description="Migrated to Litestar")
rules_bp = APIBlueprint("rules_bp", __name__, url_prefix="/admin/rules", abp_tags=[tag])
