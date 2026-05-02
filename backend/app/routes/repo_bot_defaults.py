"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="repo-bot-defaults", description="Migrated to Litestar")
repo_bot_defaults_bp = APIBlueprint(
    "repo_bot_defaults",
    __name__,
    url_prefix="/admin/repo-bot-defaults",
    abp_tags=[tag],
)
