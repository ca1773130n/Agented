"""Team generation CRUD migrated to Litestar :20002 in wave 76.

Only /admin/teams/generate/stream stays on Flask.
"""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response
from ..services.rbac_service import require_role
from ..services.team_generation_service import TeamGenerationService

tag = Tag(name="team-generation", description="Team generation streaming (Flask leftover)")
team_generation_bp = APIBlueprint(
    "team_generation", __name__, url_prefix="/admin/teams", abp_tags=[tag]
)


@team_generation_bp.post("/generate/stream")
@require_role("editor", "admin")
def generate_team_config_stream():
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    description = data.get("description", "")
    if not description or len(description) < 10:
        return error_response(
            "BAD_REQUEST",
            "description is required and must be at least 10 characters",
            HTTPStatus.BAD_REQUEST,
        )

    def generate():
        yield from TeamGenerationService.generate_streaming(description)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
