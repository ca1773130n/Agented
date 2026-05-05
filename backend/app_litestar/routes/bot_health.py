"""v0.7.0: GET /admin/bots/health — per-bot SLA rollups.

Admin-only. Reads `triggers` + `execution_logs` for the requested
window (default 7 days, max 90) and returns one rollup per bot with
success rate, p50/p95/p99 latency, last-failure summary, and a
status pill (healthy / degraded / down / no_recent_runs).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from litestar import Router, get
from litestar.exceptions import HTTPException

from app.services.bot_health_service import compute_rollups
from app_litestar.auth_guards import requires_role


@get(
    "/health",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def get_bot_health(window_days: int = 7) -> dict[str, Any]:
    """Per-bot rollup for the requested window. Admin-only."""
    try:
        rollups = compute_rollups(window_days=window_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "window_days": window_days,
        "rollups": [asdict(r) for r in rollups],
    }


bot_health_router = Router(
    path="/admin/bots",
    route_handlers=[get_bot_health],
)
