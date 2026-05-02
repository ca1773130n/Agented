"""Migrated to Litestar :20002 in wave 71 — see app_litestar/routes/leaf_crud_g.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="sketches", description="Migrated to Litestar")
sketches_bp = APIBlueprint("sketches", __name__, url_prefix="/admin/sketches", abp_tags=[tag])
