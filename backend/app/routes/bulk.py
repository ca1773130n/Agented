"""Migrated to Litestar :20002 in wave 70 — see app_litestar/routes/leaf_crud_f.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="bulk", description="Migrated to Litestar")
bulk_bp = APIBlueprint("bulk", __name__, url_prefix="/admin/bulk", abp_tags=[tag])
