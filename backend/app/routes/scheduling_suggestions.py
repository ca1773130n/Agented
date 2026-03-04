"""Scheduling suggestion API routes."""

from typing import Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..models.analytics import SchedulingSuggestionsResponse
from ..services.scheduling_suggestion_service import SchedulingSuggestionService

tag = Tag(name="scheduling-suggestions", description="Smart scheduling optimization")
scheduling_bp = APIBlueprint(
    "scheduling_suggestions", __name__, url_prefix="/admin", abp_tags=[tag]
)


class SchedulingSuggestionsQuery(BaseModel):
    """Query parameters for scheduling suggestions."""

    trigger_id: Optional[str] = Field(None, description="Filter by trigger ID")


@scheduling_bp.get(
    "/analytics/scheduling-suggestions",
    summary="Get smart scheduling suggestions based on historical execution patterns",
    responses={200: SchedulingSuggestionsResponse},
)
def get_scheduling_suggestions(query: SchedulingSuggestionsQuery):
    """Analyze execution history and suggest optimal trigger times.

    Returns top 3 hours and top 2 days ranked by success rate and duration.
    Requires at least 10 historical executions for meaningful suggestions.
    """
    result = SchedulingSuggestionService.get_suggestions(trigger_id=query.trigger_id)
    return result.model_dump()
