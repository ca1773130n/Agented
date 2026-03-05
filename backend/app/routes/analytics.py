"""Analytics API endpoints for cost, execution, and effectiveness metrics."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..services.analytics_service import AnalyticsService

tag = Tag(name="analytics", description="Analytics and metrics")
analytics_bp = APIBlueprint("analytics", __name__, url_prefix="/admin", abp_tags=[tag])


@analytics_bp.get("/analytics/cost")
def get_cost_analytics():
    """Get cost analytics aggregated by entity and time period."""
    group_by = request.args.get("group_by", "day")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    entity_type = request.args.get("entity_type")

    if group_by not in ("day", "week", "month"):
        return {"error": "group_by must be 'day', 'week', or 'month'"}, HTTPStatus.BAD_REQUEST

    result = AnalyticsService.get_cost_summary(
        entity_type=entity_type,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )
    return result, HTTPStatus.OK


@analytics_bp.get("/analytics/executions")
def get_execution_analytics():
    """Get execution analytics with volume, success/failure counts, and duration by period."""
    group_by = request.args.get("group_by", "day")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    trigger_id = request.args.get("trigger_id")
    team_id = request.args.get("team_id")

    if group_by not in ("day", "week", "month"):
        return {"error": "group_by must be 'day', 'week', or 'month'"}, HTTPStatus.BAD_REQUEST

    result = AnalyticsService.get_execution_summary(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        trigger_id=trigger_id,
        team_id=team_id,
    )
    return result, HTTPStatus.OK


@analytics_bp.get("/analytics/effectiveness")
def get_effectiveness_analytics():
    """Get PR review effectiveness with acceptance rate and time-series breakdown."""
    trigger_id = request.args.get("trigger_id")
    group_by = request.args.get("group_by", "day")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if group_by not in ("day", "week", "month"):
        return {"error": "group_by must be 'day', 'week', or 'month'"}, HTTPStatus.BAD_REQUEST

    result = AnalyticsService.get_effectiveness(
        trigger_id=trigger_id,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )
    return result, HTTPStatus.OK
