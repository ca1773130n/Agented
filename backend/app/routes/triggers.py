"""Migrated to Litestar :20002 in wave 52 — see app_litestar/routes/triggers.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="Triggers", description="Migrated to Litestar")
triggers_bp = APIBlueprint("triggers", __name__, url_prefix="/admin/triggers", abp_tags=[tag])
