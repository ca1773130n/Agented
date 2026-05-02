"""Migrated to Litestar :20002 in wave 65 — see app_litestar/routes/leaf_crud_a.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="Prompt Snippets", description="Migrated to Litestar")
prompt_snippets_bp = APIBlueprint(
    "prompt_snippets",
    __name__,
    url_prefix="/admin/prompt-snippets",
    abp_tags=[tag],
)
