"""Migrated to Litestar :20002 in wave 49 — see app_litestar/routes/admin_misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="execution-search", description="Migrated to Litestar")
execution_search_bp = APIBlueprint("execution_search", __name__, url_prefix="/admin", abp_tags=[tag])
