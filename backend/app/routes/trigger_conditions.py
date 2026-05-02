"""Migrated to Litestar :20002 in wave 65 — see app_litestar/routes/leaf_crud_a.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="trigger-conditions", description="Migrated to Litestar")
trigger_conditions_bp = APIBlueprint(
    "trigger_conditions",
    __name__,
    url_prefix="/admin",
    abp_tags=[tag],
)
