"""Migrated to Litestar :20002 in wave 66 — see app_litestar/routes/leaf_crud_b.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="pr-reviews", description="Migrated to Litestar")
pr_reviews_bp = APIBlueprint(
    "pr_reviews", __name__, url_prefix="/api/pr-reviews", abp_tags=[tag]
)
