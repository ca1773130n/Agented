"""Migrated to Litestar :20002 in wave 66 — see app_litestar/routes/leaf_crud_b.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="audit", description="Migrated to Litestar")
audit_bp = APIBlueprint("audit", __name__, url_prefix="/api/audit", abp_tags=[tag])
