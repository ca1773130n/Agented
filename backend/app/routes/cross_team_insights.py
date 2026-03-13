"""Cross-team insights API endpoint."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.db.cross_team_insights import get_cross_team_insights

tag = Tag(name="analytics", description="Analytics and metrics")
cross_team_insights_bp = APIBlueprint(
    "cross_team_insights", __name__, url_prefix="/admin", abp_tags=[tag]
)


@cross_team_insights_bp.get("/analytics/cross-team-insights")
def get_cross_team_insights_endpoint():
    """Get cross-team automation insights including per-team execution stats and org-level findings."""
    result = get_cross_team_insights()
    return result, HTTPStatus.OK
