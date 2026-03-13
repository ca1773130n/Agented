"""Quality ratings API endpoints for agent output scoring."""

from http import HTTPStatus
from typing import Optional

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.quality_ratings import get_bot_quality_stats, get_quality_entries, upsert_quality_rating

tag = Tag(name="quality_ratings", description="Agent execution quality ratings and stats")
quality_ratings_bp = APIBlueprint(
    "quality_ratings", __name__, url_prefix="/admin/quality", abp_tags=[tag]
)


class QualityRatingPath(BaseModel):
    """Path parameter for quality rating endpoint."""

    execution_id: str = Field(..., description="Execution ID to rate")


class QualityRatingBody(BaseModel):
    """Request body for submitting a quality rating."""

    rating: int = Field(..., ge=1, le=5, description="Quality score from 1 to 5")
    feedback: str = Field("", description="Optional free-text feedback")
    trigger_id: Optional[str] = Field(None, description="Trigger ID associated with the execution")


@quality_ratings_bp.get("/entries")
def list_quality_entries():
    """List execution quality rating entries with output preview.

    Query params:
        trigger_id: Filter by trigger ID (optional).
        limit: Max results (default 50).
        offset: Pagination offset (default 0).
    """
    trigger_id = request.args.get("trigger_id") or None
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return error_response(
            "BAD_REQUEST", "limit and offset must be integers", HTTPStatus.BAD_REQUEST
        )

    if limit < 1 or limit > 200:
        return error_response(
            "BAD_REQUEST", "limit must be between 1 and 200", HTTPStatus.BAD_REQUEST
        )

    entries = get_quality_entries(trigger_id=trigger_id, limit=limit, offset=offset)
    return {"entries": entries, "total": len(entries)}, HTTPStatus.OK


@quality_ratings_bp.post("/entries/<string:execution_id>")
def submit_quality_rating(path: QualityRatingPath, body: QualityRatingBody):
    """Submit or update a quality rating for an execution.

    Path params:
        execution_id: The execution to rate.

    Body:
        rating (int): Score 1-5 (required).
        feedback (str): Optional text feedback.
        trigger_id (str): Optional trigger ID override.
    """
    try:
        result = upsert_quality_rating(
            execution_id=path.execution_id,
            trigger_id=body.trigger_id,
            rating=body.rating,
            feedback=body.feedback,
        )
        return result, HTTPStatus.OK
    except ValueError as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)
    except Exception as e:
        return error_response("INTERNAL_ERROR", str(e), HTTPStatus.INTERNAL_SERVER_ERROR)


@quality_ratings_bp.get("/stats")
def get_quality_stats():
    """Get aggregated quality statistics per bot/trigger."""
    stats = get_bot_quality_stats()
    return {"bots": stats}, HTTPStatus.OK
