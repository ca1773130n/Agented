"""Migrated to Litestar :20002 in wave 67 — see app_litestar/routes/leaf_crud_c.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="products", description="Migrated to Litestar")
products_bp = APIBlueprint(
    "products", __name__, url_prefix="/admin/products", abp_tags=[tag]
)
