"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="health-monitor", description="Migrated to Litestar")
health_monitor_bp = APIBlueprint(
    "health_monitor", __name__, url_prefix="/admin/health-monitor", abp_tags=[tag]
)
