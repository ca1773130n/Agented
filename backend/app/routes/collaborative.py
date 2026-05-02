"""Migrated to Litestar :20002 in wave 68 — see app_litestar/routes/leaf_crud_d.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="collaborative", description="Migrated to Litestar")
collaborative_bp = APIBlueprint("collaborative", __name__, url_prefix="/admin", abp_tags=[tag])
