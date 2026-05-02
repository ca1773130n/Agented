"""Migrated to Litestar :20002 in wave 60."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="tracing", description="Migrated to Litestar")
tracing_bp = APIBlueprint("tracing_bp", __name__, url_prefix="/admin", abp_tags=[tag])
