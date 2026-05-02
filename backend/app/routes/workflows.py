"""Migrated to Litestar :20002 in wave 62 — see app_litestar/routes/workflows.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="workflows", description="Migrated to Litestar")
workflows_bp = APIBlueprint("workflows", __name__, url_prefix="/admin/workflows", abp_tags=[tag])
