"""Migrated to Litestar :20002 in wave 52 (now /admin/triggers is on Litestar)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="payload-transformers", description="Migrated to Litestar")
payload_transformers_bp = APIBlueprint(
    "payload_transformers", __name__, url_prefix="/admin", abp_tags=[tag]
)
