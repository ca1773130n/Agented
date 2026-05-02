"""Migrated to Litestar :20002 in wave 67 — see app_litestar/routes/leaf_crud_c.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="Findings", description="Migrated to Litestar")
findings_bp = APIBlueprint("findings", __name__, url_prefix="/api", abp_tags=[tag])
