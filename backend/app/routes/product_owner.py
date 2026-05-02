"""Migrated to Litestar :20002 in wave 58 — see app_litestar/routes/product_owner.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="product-owner", description="Migrated to Litestar")
product_owner_bp = APIBlueprint(
    "product_owner", __name__, url_prefix="/admin/products", abp_tags=[tag]
)
