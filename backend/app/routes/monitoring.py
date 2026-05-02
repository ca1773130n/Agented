"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="monitoring", description="Migrated to Litestar")
monitoring_bp = APIBlueprint(
    "monitoring", __name__, url_prefix="/admin/monitoring", abp_tags=[tag]
)
