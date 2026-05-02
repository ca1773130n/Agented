"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="secrets", description="Migrated to Litestar")
secrets_bp = APIBlueprint("secrets_bp", __name__, url_prefix="/admin/secrets", abp_tags=[tag])
