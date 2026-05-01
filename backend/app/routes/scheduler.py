"""Migrated to Litestar :20002 in wave 51."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="scheduler", description="Migrated to Litestar")
scheduler_bp = APIBlueprint("scheduler", __name__, url_prefix="/admin/scheduler", abp_tags=[tag])
