"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="onboarding", description="Migrated to Litestar")
onboarding_bp = APIBlueprint("onboarding", __name__, url_prefix="/admin", abp_tags=[tag])
