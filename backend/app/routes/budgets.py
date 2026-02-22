"""Budget management API endpoints."""

from datetime import datetime, timedelta
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    delete_budget_limit,
    get_all_budget_limits,
    get_budget_limit,
    get_current_period_spend,
    get_rate_limit_stats_by_period,
    get_token_usage_count,
    get_token_usage_summary,
    get_token_usage_total_cost,
    get_usage_aggregated_summary,
    get_usage_by_entity,
    set_budget_limit,
)
from ..services.budget_service import BudgetService
from ..services.session_usage_collector import SessionUsageCollector

tag = Tag(name="budgets", description="Budget management and token usage tracking")
budgets_bp = APIBlueprint("budgets", __name__, url_prefix="/admin/budgets", abp_tags=[tag])


class BudgetEntityPath(BaseModel):
    entity_type: str = Field(..., description="Entity type (agent, team, or trigger)")
    entity_id: str = Field(..., description="Entity ID")


@budgets_bp.get("/window-usage")
def get_window_usage():
    """Get approximate rate limit window usage (5-hour and weekly)."""
    result = BudgetService.get_window_usage()
    return result, HTTPStatus.OK


@budgets_bp.get("/limits")
def list_budget_limits():
    """List all budget limits with current spend."""
    limits = get_all_budget_limits()

    # Enrich each limit with current spend
    enriched = []
    for limit in limits:
        current_spend = get_current_period_spend(
            limit["entity_type"], limit["entity_id"], limit.get("period", "monthly")
        )
        entry = dict(limit)
        entry["current_spend_usd"] = current_spend
        enriched.append(entry)

    return {"limits": enriched}, HTTPStatus.OK


@budgets_bp.get("/limits/<entity_type>/<entity_id>")
def get_budget_limit_detail(path: BudgetEntityPath):
    """Get budget limit for a specific entity."""
    limit = get_budget_limit(path.entity_type, path.entity_id)
    if not limit:
        return {"error": "No budget limit found for this entity"}, HTTPStatus.NOT_FOUND

    current_spend = get_current_period_spend(
        path.entity_type, path.entity_id, limit.get("period", "monthly")
    )
    result = dict(limit)
    result["current_spend_usd"] = current_spend
    return result, HTTPStatus.OK


@budgets_bp.put("/limits")
def set_budget_limit_endpoint():
    """Set or update a budget limit."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    # Validate required fields
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    if not entity_type or not entity_id:
        return {"error": "entity_type and entity_id are required"}, HTTPStatus.BAD_REQUEST

    if entity_type not in ("agent", "team", "trigger"):
        return {
            "error": "entity_type must be 'agent', 'team', or 'trigger'"
        }, HTTPStatus.BAD_REQUEST

    period = data.get("period", "monthly")
    if period not in ("daily", "weekly", "monthly"):
        return {"error": "period must be 'daily', 'weekly', or 'monthly'"}, HTTPStatus.BAD_REQUEST

    soft_limit_usd = data.get("soft_limit_usd")
    hard_limit_usd = data.get("hard_limit_usd")

    if soft_limit_usd is None and hard_limit_usd is None:
        return {
            "error": "At least one of soft_limit_usd or hard_limit_usd must be set"
        }, HTTPStatus.BAD_REQUEST

    if (
        soft_limit_usd is not None
        and hard_limit_usd is not None
        and hard_limit_usd < soft_limit_usd
    ):
        return {"error": "hard_limit_usd must be >= soft_limit_usd"}, HTTPStatus.BAD_REQUEST

    success = set_budget_limit(
        entity_type=entity_type,
        entity_id=entity_id,
        period=period,
        soft_limit_usd=soft_limit_usd,
        hard_limit_usd=hard_limit_usd,
    )

    if not success:
        return {"error": "Failed to set budget limit"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Return the saved limit
    limit = get_budget_limit(entity_type, entity_id)
    current_spend = get_current_period_spend(entity_type, entity_id, period)
    result = dict(limit)
    result["current_spend_usd"] = current_spend
    return result, HTTPStatus.OK


@budgets_bp.delete("/limits/<entity_type>/<entity_id>")
def delete_budget_limit_endpoint(path: BudgetEntityPath):
    """Delete a budget limit."""
    deleted = delete_budget_limit(path.entity_type, path.entity_id)
    if not deleted:
        return {"error": "No budget limit found for this entity"}, HTTPStatus.NOT_FOUND
    return "", HTTPStatus.NO_CONTENT


@budgets_bp.post("/check")
def check_budget_endpoint():
    """Pre-execution budget check."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    if not entity_type or not entity_id:
        return {"error": "entity_type and entity_id are required"}, HTTPStatus.BAD_REQUEST

    result = BudgetService.check_budget(entity_type, entity_id)

    # Sanitize limit dict if present (sqlite Row objects are not JSON-serializable)
    if "limit" in result and result["limit"]:
        result["limit"] = dict(result["limit"])

    return result, HTTPStatus.OK


@budgets_bp.post("/estimate")
def estimate_cost_endpoint():
    """Estimate execution cost."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    prompt = data.get("prompt")
    if not prompt:
        return {"error": "prompt is required"}, HTTPStatus.BAD_REQUEST

    model = data.get("model", "claude-sonnet-4")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")

    result = BudgetService.estimate_cost(
        prompt=prompt,
        model=model,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return result, HTTPStatus.OK


@budgets_bp.get("/usage")
def get_usage():
    """Get token usage records with filtering."""
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    usage = get_token_usage_summary(
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    total_cost = get_token_usage_total_cost(
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    total_records = get_token_usage_count(
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "usage": usage,
        "total_cost_usd": total_cost,
        "total_records": total_records,
    }, HTTPStatus.OK


@budgets_bp.get("/usage/summary")
def get_usage_summary():
    """Get aggregated usage summary."""
    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    group_by = request.args.get("group_by", "day")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if group_by not in ("day", "week", "month"):
        return {"error": "group_by must be 'day', 'week', or 'month'"}, HTTPStatus.BAD_REQUEST

    summary = get_usage_aggregated_summary(
        group_by=group_by,
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {"summary": summary}, HTTPStatus.OK


@budgets_bp.get("/usage/by-entity")
def get_usage_by_entity_endpoint():
    """Get usage breakdown by entity."""
    entity_type = request.args.get("entity_type")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    entities = get_usage_by_entity(
        entity_type=entity_type,
        start_date=start_date,
        end_date=end_date,
    )

    return {"entities": entities}, HTTPStatus.OK


@budgets_bp.get("/usage/all-time")
def get_all_time_usage():
    """Get all-time total spend from the token_usage table."""
    total = get_token_usage_total_cost()
    return {"total_cost_usd": total}, HTTPStatus.OK


@budgets_bp.post("/collect-sessions")
def collect_session_usage():
    """Scan local CLI session files and import token usage data."""
    try:
        results = SessionUsageCollector.collect_all()
        return {"collected": results}, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Collection failed: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@budgets_bp.get("/session-stats")
def get_session_stats():
    """Get quick aggregate from Claude Code's stats-cache.json."""
    stats = SessionUsageCollector.get_stats_cache_summary()
    if stats is None:
        return {"stats": None, "message": "No stats-cache.json found"}, HTTPStatus.OK
    return {"stats": stats}, HTTPStatus.OK


@budgets_bp.get("/usage/history-stats")
def get_history_stats():
    """Get historical usage stats grouped by week or month."""
    period = request.args.get("period", "weekly")
    months_back = request.args.get("months_back", 6, type=int)

    if period not in ("weekly", "monthly"):
        return {"error": "period must be 'weekly' or 'monthly'"}, HTTPStatus.BAD_REQUEST

    group_by = "week" if period == "weekly" else "month"

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")

    usage_summary = get_usage_aggregated_summary(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )

    rate_stats = get_rate_limit_stats_by_period(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )

    # Merge rate stats into usage periods by period_start
    rate_map = {r["period_start"]: r for r in rate_stats}

    periods = []
    for u in usage_summary:
        rate = rate_map.get(u["period_start"], {})
        periods.append(
            {
                "period_start": u["period_start"],
                "total_cost_usd": u["total_cost_usd"],
                "total_input_tokens": u["total_input_tokens"],
                "total_output_tokens": u["total_output_tokens"],
                "execution_count": u["execution_count"],
                "avg_rate_limit_pct": rate.get("avg_percentage"),
                "max_rate_limit_pct": rate.get("max_percentage"),
                "snapshot_count": rate.get("snapshot_count", 0),
            }
        )

    # Include rate-only periods not in usage data
    usage_keys = {u["period_start"] for u in usage_summary}
    for r in rate_stats:
        if r["period_start"] not in usage_keys:
            periods.append(
                {
                    "period_start": r["period_start"],
                    "total_cost_usd": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "execution_count": 0,
                    "avg_rate_limit_pct": r.get("avg_percentage"),
                    "max_rate_limit_pct": r.get("max_percentage"),
                    "snapshot_count": r.get("snapshot_count", 0),
                }
            )

    periods.sort(key=lambda p: p["period_start"], reverse=True)

    return {"period_type": period, "periods": periods}, HTTPStatus.OK
