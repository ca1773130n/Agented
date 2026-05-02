"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="project-instances", description="Migrated to Litestar")
project_instances_bp = APIBlueprint(
    "project_instances", __name__, url_prefix="/admin/projects", abp_tags=[tag]
)
