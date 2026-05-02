"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="gitops", description="Migrated to Litestar")
gitops_bp = APIBlueprint("gitops_bp", __name__, url_prefix="/admin", abp_tags=[tag])
