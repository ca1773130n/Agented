"""Migrated to Litestar :20002 in wave 68 — see app_litestar/routes/leaf_crud_d.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="knowledge-graph", description="Migrated to Litestar")
knowledge_graph_bp = APIBlueprint("knowledge_graph", __name__, url_prefix="/admin", abp_tags=[tag])
