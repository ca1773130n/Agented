"""Migrated to Litestar :20002 in wave 48 — see app_litestar/routes/misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="scheduling-suggestions", description="Migrated to Litestar")
scheduling_bp = APIBlueprint("scheduling_suggestions", __name__, url_prefix="/admin", abp_tags=[tag])
