"""Migrated to Litestar :20002 in wave 66 — see app_litestar/routes/leaf_crud_b.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="marketplaces", description="Migrated to Litestar")
marketplace_bp = APIBlueprint(
    "marketplaces", __name__, url_prefix="/admin/marketplaces", abp_tags=[tag]
)
