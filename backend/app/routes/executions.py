"""Migrated to Litestar :20002 (waves 75 + 78). All execution routes including the SSE stream now live on Litestar."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="executions", description="Migrated to Litestar")
executions_bp = APIBlueprint("executions", __name__, url_prefix="/admin", abp_tags=[tag])
