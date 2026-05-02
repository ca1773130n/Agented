"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="system", description="Migrated to Litestar")
system_bp = APIBlueprint("system_bp", __name__, url_prefix="/admin/system", abp_tags=[tag])
