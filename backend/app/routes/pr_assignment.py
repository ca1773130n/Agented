"""Migrated to Litestar :20002 in wave 68 — see app_litestar/routes/leaf_crud_d.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="pr-assignment", description="Migrated to Litestar")
pr_assignment_bp = APIBlueprint(
    "pr_assignment", __name__, url_prefix="/api/pr-assignment", abp_tags=[tag]
)
