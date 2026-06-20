"""Admin routes for session takeaways (positive-learning capture)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import NotFoundException

from app.db import harness_takeaways as repo


@get("/projects/{project_id:str}/takeaways", sync_to_thread=False)
def list_project_takeaways(
    project_id: str,
    kind: Optional[str] = None,
    applied: Optional[bool] = None,
    dismissed: Optional[bool] = None,
    limit: int = 50,
) -> dict[str, Any]:
    capped = max(1, min(int(limit or 50), 200))
    return {
        "project_id": project_id,
        "takeaways": repo.list_for_project(
            project_id,
            kind=kind,
            applied=applied,
            dismissed=dismissed,
            limit=capped,
        ),
    }


@get("/takeaways/recent", sync_to_thread=False)
def list_recent_takeaways(
    limit: int = 25,
    applied: Optional[bool] = None,
    dismissed: Optional[bool] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    capped = max(1, min(int(limit or 25), 200))
    return {
        "takeaways": repo.list_recent(
            project_id=project_id,
            applied=applied,
            dismissed=dismissed,
            limit=capped,
        ),
    }


@get("/takeaways/{takeaway_id:str}", sync_to_thread=False)
def get_takeaway(takeaway_id: str) -> dict[str, Any]:
    row = repo.get(takeaway_id)
    if row is None:
        raise NotFoundException(detail=f"takeaway not found: {takeaway_id}")
    return row


@post("/takeaways/{takeaway_id:str}/apply", sync_to_thread=True)
def apply_takeaway_route(takeaway_id: str) -> dict[str, Any]:
    from app.services.harness_takeaway_extractor import apply_takeaway

    return apply_takeaway(takeaway_id)


@post("/takeaways/{takeaway_id:str}/dismiss", sync_to_thread=True)
def dismiss_takeaway_route(
    takeaway_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_takeaway_extractor import dismiss_takeaway

    reason = (data or {}).get("reason")
    return dismiss_takeaway(takeaway_id, reason=reason)


harness_takeaways_router = Router(
    path="/admin",
    route_handlers=[
        list_project_takeaways,
        list_recent_takeaways,
        get_takeaway,
        apply_takeaway_route,
        dismiss_takeaway_route,
    ],
)
