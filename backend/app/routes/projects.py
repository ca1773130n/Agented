"""Migrated to Litestar :20002 in wave 55 — see app_litestar/routes/projects.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="projects", description="Migrated to Litestar")
projects_bp = APIBlueprint("projects", __name__, url_prefix="/admin/projects", abp_tags=[tag])
