"""Migrated to Litestar :20002 in wave 71 — see app_litestar/routes/leaf_crud_g.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="plugin-exports", description="Migrated to Litestar")
plugin_exports_bp = APIBlueprint(
    "plugin_exports",
    __name__,
    url_prefix="/admin/plugin-exports",
    abp_tags=[tag],
)
