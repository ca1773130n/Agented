"""Budgets routes (track A, wave 59) — 14 routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
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
from app.services.budget_service import BudgetService
from app.services.session_usage_collector import SessionUsageCollector


@get("/window-usage", sync_to_thread=False)
def window_usage() -> dict[str, Any]:
    return BudgetService.get_window_usage()


@get("/limits", sync_to_thread=False)
def list_limits(
    limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    from app.db.budgets import count_all_budget_limits

    rows = get_all_budget_limits(limit=limit, offset=offset or 0)
    enriched = []
    for row in rows:
        spend = get_current_period_spend(
            row["entity_type"], row["entity_id"], row.get("period", "monthly")
        )
        entry = dict(row)
        entry["current_spend_usd"] = spend
        enriched.append(entry)
    return {"limits": enriched, "total_count": count_all_budget_limits()}


@get("/limits/{entity_type:str}/{entity_id:str}", sync_to_thread=False)
def get_limit(entity_type: str, entity_id: str) -> dict[str, Any]:
    limit = get_budget_limit(entity_type, entity_id)
    if not limit:
        raise NotFoundException(detail="No budget limit found for this entity")
    result = dict(limit)
    result["current_spend_usd"] = get_current_period_spend(
        entity_type, entity_id, limit.get("period", "monthly")
    )
    return result


@put("/limits", sync_to_thread=False)
def set_limit(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    if not entity_type or not entity_id:
        raise ClientException(detail="entity_type and entity_id are required")
    if entity_type not in ("agent", "team", "trigger"):
        raise ClientException(
            detail="entity_type must be 'agent', 'team', or 'trigger'"
        )
    period = data.get("period", "monthly")
    if period not in ("daily", "weekly", "monthly"):
        raise ClientException(
            detail="period must be 'daily', 'weekly', or 'monthly'"
        )
    soft = data.get("soft_limit_usd")
    hard = data.get("hard_limit_usd")
    if soft is None and hard is None:
        raise ClientException(
            detail="At least one of soft_limit_usd or hard_limit_usd must be set"
        )
    if soft is not None and hard is not None and hard < soft:
        raise ClientException(detail="hard_limit_usd must be >= soft_limit_usd")
    if not set_budget_limit(
        entity_type=entity_type,
        entity_id=entity_id,
        period=period,
        soft_limit_usd=soft,
        hard_limit_usd=hard,
    ):
        raise HTTPException(status_code=500, detail="Failed to set budget limit")
    limit = get_budget_limit(entity_type, entity_id)
    result = dict(limit)
    result["current_spend_usd"] = get_current_period_spend(
        entity_type, entity_id, period
    )
    return result


@delete(
    "/limits/{entity_type:str}/{entity_id:str}",
    status_code=204,
    sync_to_thread=False,
)
def delete_limit(entity_type: str, entity_id: str) -> None:
    if not delete_budget_limit(entity_type, entity_id):
        raise NotFoundException(detail="No budget limit found for this entity")
    return None


@post("/check", sync_to_thread=False)
def check_budget(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    if not entity_type or not entity_id:
        raise ClientException(detail="entity_type and entity_id are required")
    result = BudgetService.check_budget(entity_type, entity_id)
    if "limit" in result and result["limit"]:
        result["limit"] = dict(result["limit"])
    return result


@post("/estimate", sync_to_thread=False)
def estimate_cost(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    prompt = data.get("prompt")
    if not prompt:
        raise ClientException(detail="prompt is required")
    return BudgetService.estimate_cost(
        prompt=prompt,
        model=data.get("model", "claude-sonnet-4"),
        entity_type=data.get("entity_type"),
        entity_id=data.get("entity_id"),
    )


@get("/usage", sync_to_thread=False)
def get_usage(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    usage = get_token_usage_summary(
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {
        "usage": usage,
        "total_cost_usd": get_token_usage_total_cost(
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
        ),
        "total_records": get_token_usage_count(
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
        ),
    }


@get("/usage/summary", sync_to_thread=False)
def usage_summary(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    if group_by not in ("day", "week", "month"):
        raise ClientException(detail="group_by must be 'day', 'week', or 'month'")
    return {
        "summary": get_usage_aggregated_summary(
            group_by=group_by,
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
        )
    }


@get("/usage/by-entity", sync_to_thread=False)
def usage_by_entity(
    entity_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "entities": get_usage_by_entity(
            entity_type=entity_type, start_date=start_date, end_date=end_date
        )
    }


@get("/usage/all-time", sync_to_thread=False)
def all_time_usage() -> dict[str, Any]:
    return {"total_cost_usd": get_token_usage_total_cost()}


# Heavy: collect_all() recursively walks every Claude/Codex session .jsonl
# on disk and writes to SQLite — multi-second on large histories. It MUST run
# in a worker thread; with sync_to_thread=False it executes on the single
# UvicornWorker's event loop (workers=1) and freezes the whole backend, so
# concurrent reads (monitoring/status, usage, even /health) hang until it
# finishes. That starvation is what blanked the Cost dashboard's rate-limit
# graphs. See gunicorn.conf.py (workers=1 is mandatory).
@post("/collect-sessions", sync_to_thread=True)
def collect_session_usage() -> dict[str, Any]:
    try:
        return {"collected": SessionUsageCollector.collect_all()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Collection failed: {exc}"
        ) from None


@get("/session-stats", sync_to_thread=False)
def session_stats() -> dict[str, Any]:
    stats = SessionUsageCollector.get_stats_cache_summary()
    if stats is None:
        return {"stats": None, "message": "No stats-cache.json found"}
    return {"stats": stats}


@get("/usage/history-stats", sync_to_thread=False)
def history_stats(period: str = "weekly", months_back: int = 6) -> dict[str, Any]:
    if period not in ("weekly", "monthly"):
        raise ClientException(detail="period must be 'weekly' or 'monthly'")
    group_by = "week" if period == "weekly" else "month"
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=months_back * 30)).strftime(
        "%Y-%m-%d"
    )
    usage = get_usage_aggregated_summary(
        group_by=group_by, start_date=start_date, end_date=end_date
    )
    rate_stats = get_rate_limit_stats_by_period(
        group_by=group_by, start_date=start_date, end_date=end_date
    )
    rate_map = {r["period_start"]: r for r in rate_stats}
    periods = []
    for u in usage:
        rate = rate_map.get(u["period_start"], {})
        periods.append(
            {
                "period_start": u["period_start"],
                "total_cost_usd": u["total_cost_usd"],
                "total_input_tokens": u["total_input_tokens"],
                "total_output_tokens": u["total_output_tokens"],
                "total_cache_read_tokens": u.get("total_cache_read_tokens", 0),
                "total_cache_creation_tokens": u.get("total_cache_creation_tokens", 0),
                "execution_count": u["execution_count"],
                "avg_rate_limit_pct": rate.get("avg_percentage"),
                "max_rate_limit_pct": rate.get("max_percentage"),
                "snapshot_count": rate.get("snapshot_count", 0),
            }
        )
    usage_keys = {u["period_start"] for u in usage}
    for r in rate_stats:
        if r["period_start"] not in usage_keys:
            periods.append(
                {
                    "period_start": r["period_start"],
                    "total_cost_usd": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cache_read_tokens": 0,
                    "total_cache_creation_tokens": 0,
                    "execution_count": 0,
                    "avg_rate_limit_pct": r.get("avg_percentage"),
                    "max_rate_limit_pct": r.get("max_percentage"),
                    "snapshot_count": r.get("snapshot_count", 0),
                }
            )
    periods.sort(key=lambda p: p["period_start"], reverse=True)
    return {"period_type": period, "periods": periods}


budgets_router = Router(
    path="/admin/budgets",
    route_handlers=[
        window_usage,
        list_limits,
        get_limit,
        set_limit,
        delete_limit,
        check_budget,
        estimate_cost,
        get_usage,
        usage_summary,
        usage_by_entity,
        all_time_usage,
        collect_session_usage,
        session_stats,
        history_stats,
    ],
)
