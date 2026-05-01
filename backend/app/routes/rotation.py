"""Migrated to Litestar :20002 in wave 49 — see app_litestar/routes/admin_misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="rotation", description="Migrated to Litestar")
rotation_bp = APIBlueprint("rotation", __name__, url_prefix="/admin/rotation", abp_tags=[tag])
