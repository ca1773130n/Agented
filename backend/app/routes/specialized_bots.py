"""Migrated to Litestar :20002 in wave 49 — see app_litestar/routes/admin_misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="specialized-bots", description="Migrated to Litestar")
specialized_bots_bp = APIBlueprint("specialized_bots", __name__, url_prefix="/admin", abp_tags=[tag])
