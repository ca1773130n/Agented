"""v0.7.7: admin endpoints for super-agent activity inspector.

Three GET endpoints power the inspector page:
- ``/admin/super-agents/{id}/activity`` — timeline list with limit/since/types filters.
- ``/admin/super-agents/{id}/rollup`` — header-card stats (event count,
  cost, status pill, error rate).
- ``/admin/super-agents/sessions/{session_id}/activity`` — per-session
  timeline drill-down.

All require admin via ``requires_role("admin")``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from litestar import Router, get
from litestar.exceptions import HTTPException

from app.services import super_agent_activity_service
from app_litestar.auth_guards import requires_role


@get(
    "/{super_agent_id:str}/activity",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def list_activity(
    super_agent_id: str,
    limit: int = 200,
    since: str | None = None,
    types: str | None = None,
) -> dict[str, Any]:
    type_list = [t.strip() for t in types.split(",")] if types else None
    return {
        "events": super_agent_activity_service.list_for_super_agent(
            super_agent_id,
            limit=limit,
            since=since,
            types=type_list,
        )
    }


@get(
    "/{super_agent_id:str}/rollup",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def get_rollup(super_agent_id: str, window_days: int = 7) -> dict[str, Any]:
    try:
        r = super_agent_activity_service.rollup(super_agent_id, window_days=window_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@get(
    "/sessions/{session_id:str}/activity",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def list_session_activity(session_id: str, limit: int = 200) -> dict[str, Any]:
    return {"events": super_agent_activity_service.list_for_session(session_id, limit=limit)}


super_agent_activity_router = Router(
    path="/admin/super-agents",
    route_handlers=[list_activity, get_rollup, list_session_activity],
)
