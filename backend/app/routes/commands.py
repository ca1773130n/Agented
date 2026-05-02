"""Migrated to Litestar :20002 in wave 61."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="commands", description="Migrated to Litestar")
commands_bp = APIBlueprint("commands_bp", __name__, url_prefix="/admin/commands", abp_tags=[tag])
