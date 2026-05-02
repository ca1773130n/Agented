"""Migrated to Litestar :20002 in wave 67 — see app_litestar/routes/leaf_crud_c.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="report-digests", description="Migrated to Litestar")
report_digests_bp = APIBlueprint("report_digests", __name__, url_prefix="/admin", abp_tags=[tag])
