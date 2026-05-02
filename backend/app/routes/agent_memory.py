"""Migrated to Litestar :20002 in wave 70 — see app_litestar/routes/leaf_crud_f.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="agent-memory", description="Migrated to Litestar")
agent_memory_bp = APIBlueprint("agent_memory", __name__, url_prefix="/admin", abp_tags=[tag])
