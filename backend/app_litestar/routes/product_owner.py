"""Product owner routes (track A, wave 58).

Nested under /admin/products/{product_id}/* — already routed to Litestar
by wave 55's vite proxy entry, so these were 404'ing until this wave.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
    add_milestone_project,
    add_product_decision,
    add_product_milestone,
    delete_milestone_project,
    delete_product_decision,
    delete_product_milestone,
    get_decisions_by_product,
    get_milestones_by_product,
    get_product,
    get_product_decision,
    get_product_milestone,
    get_projects_for_milestone,
    update_product,
    update_product_decision,
    update_product_milestone,
)
from app.services.product_owner_service import ProductOwnerService

from ..auth import Caller


def _ensure_product(product_id: str) -> None:
    if not get_product(product_id):
        raise NotFoundException(detail="Product not found")


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@get("/{product_id:str}/decisions", sync_to_thread=False)
def list_product_decisions(
    product_id: str,
    caller: Caller,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    decisions = get_decisions_by_product(
        product_id,
        status=status,
        tag=tag,
        limit=limit,
        offset=offset or 0,
    )
    from app.db.rotations import count_decisions_by_product

    return {
        "decisions": decisions,
        "total_count": count_decisions_by_product(product_id, status=status, tag=tag),
    }


@post("/{product_id:str}/decisions", sync_to_thread=False)
def create_product_decision(
    product_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data or not data.get("title"):
        raise ClientException(detail="title is required")
    tags = data.get("tags", [])
    decision_id = add_product_decision(
        product_id=product_id,
        title=data["title"],
        description=data.get("description"),
        rationale=data.get("rationale"),
        decision_type=data.get("decision_type", "technical"),
        tags_json=json.dumps(tags) if tags else None,
    )
    if not decision_id:
        raise HTTPException(status_code=500, detail="Failed to create decision")
    return {
        "message": "Decision created",
        "decision": get_product_decision(decision_id),
    }


@get(
    "/{product_id:str}/decisions/{decision_id:str}", sync_to_thread=False
)
def get_decision(
    product_id: str, decision_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    decision = get_product_decision(decision_id)
    if not decision:
        raise NotFoundException(detail="Decision not found")
    return {"decision": decision}


@put(
    "/{product_id:str}/decisions/{decision_id:str}", sync_to_thread=False
)
def update_decision(
    product_id: str, decision_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data:
        raise ClientException(detail="JSON body required")
    kwargs = {
        k: v
        for k, v in data.items()
        if k in (
            "title", "description", "rationale", "tags_json", "status",
            "decided_by", "context_json", "decision_type",
        )
    }
    if not update_product_decision(decision_id, **kwargs):
        raise NotFoundException(detail="Decision not found or no changes")
    return {
        "message": "Decision updated",
        "decision": get_product_decision(decision_id),
    }


@delete(
    "/{product_id:str}/decisions/{decision_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_decision(
    product_id: str, decision_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not delete_product_decision(decision_id):
        raise NotFoundException(detail="Decision not found")
    return {"message": "Decision deleted"}


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


@get("/{product_id:str}/milestones", sync_to_thread=False)
def list_milestones(
    product_id: str,
    caller: Caller,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    milestones = get_milestones_by_product(
        product_id, status=status, limit=limit, offset=offset or 0
    )
    from app.db.rotations import count_milestones_by_product_owner

    return {
        "milestones": milestones,
        "total_count": count_milestones_by_product_owner(
            product_id, status=status
        ),
    }


@post("/{product_id:str}/milestones", sync_to_thread=False)
def create_milestone(
    product_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data or not data.get("version") or not data.get("title"):
        raise ClientException(detail="version and title are required")
    milestone_id = add_product_milestone(
        product_id=product_id,
        version=data["version"],
        title=data["title"],
        description=data.get("description"),
        target_date=data.get("target_date"),
        sort_order=data.get("sort_order", 0),
        progress_pct=data.get("progress_pct", 0),
    )
    if not milestone_id:
        raise HTTPException(status_code=500, detail="Failed to create milestone")
    return {
        "message": "Milestone created",
        "milestone": get_product_milestone(milestone_id),
    }


@get(
    "/{product_id:str}/milestones/{milestone_id:str}", sync_to_thread=False
)
def get_milestone(
    product_id: str, milestone_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    milestone = get_product_milestone(milestone_id)
    if not milestone:
        raise NotFoundException(detail="Milestone not found")
    milestone["projects"] = get_projects_for_milestone(milestone_id)
    return {"milestone": milestone}


@put(
    "/{product_id:str}/milestones/{milestone_id:str}", sync_to_thread=False
)
def update_milestone(
    product_id: str, milestone_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data:
        raise ClientException(detail="JSON body required")
    kwargs = {
        k: v
        for k, v in data.items()
        if k in (
            "version", "title", "description", "status", "target_date",
            "sort_order", "progress_pct", "completed_date",
        )
    }
    if not update_product_milestone(milestone_id, **kwargs):
        raise NotFoundException(detail="Milestone not found or no changes")
    return {
        "message": "Milestone updated",
        "milestone": get_product_milestone(milestone_id),
    }


@delete(
    "/{product_id:str}/milestones/{milestone_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_milestone(
    product_id: str, milestone_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not delete_product_milestone(milestone_id):
        raise NotFoundException(detail="Milestone not found")
    return {"message": "Milestone deleted"}


# ---------------------------------------------------------------------------
# Milestone-project junction
# ---------------------------------------------------------------------------


@get(
    "/{product_id:str}/milestones/{milestone_id:str}/projects",
    sync_to_thread=False,
)
def list_milestone_projects(
    product_id: str,
    milestone_id: str,
    caller: Caller,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    projects = get_projects_for_milestone(
        milestone_id, limit=limit, offset=offset or 0
    )
    from app.db.rotations import count_projects_for_milestone

    return {
        "projects": projects,
        "total_count": count_projects_for_milestone(milestone_id),
    }


@post(
    "/{product_id:str}/milestones/{milestone_id:str}/projects",
    sync_to_thread=False,
)
def link_project(
    product_id: str, milestone_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data or not data.get("project_id"):
        raise ClientException(detail="project_id is required")
    result = add_milestone_project(
        milestone_id=milestone_id,
        project_id=data["project_id"],
        contribution=data.get("contribution"),
    )
    if result is None:
        raise ClientException(
            detail="Failed to link project (already linked or invalid IDs)"
        )
    return {"message": "Project linked to milestone"}


@delete(
    "/{product_id:str}/milestones/{milestone_id:str}/projects/{project_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def unlink_project(
    product_id: str, milestone_id: str, project_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not delete_milestone_project(milestone_id, project_id):
        raise NotFoundException(detail="Link not found")
    return {"message": "Project unlinked from milestone"}


# ---------------------------------------------------------------------------
# Owner / meetings / dashboard
# ---------------------------------------------------------------------------


@put("/{product_id:str}/owner", sync_to_thread=False)
def assign_owner(
    product_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    if not data or "owner_agent_id" not in data:
        raise ClientException(detail="owner_agent_id is required")
    update_product(product_id, owner_agent_id=data["owner_agent_id"])
    return {"message": "Owner assigned", "product": get_product(product_id)}


@post("/{product_id:str}/meetings/standup", sync_to_thread=False)
def trigger_standup(product_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    try:
        return ProductOwnerService.trigger_standup_meeting(product_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None


@get("/{product_id:str}/meetings/history", sync_to_thread=False)
def meeting_history(product_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    return {"meetings": ProductOwnerService.get_meeting_history(product_id)}


@get("/{product_id:str}/dashboard", sync_to_thread=False)
def get_dashboard(product_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    _ensure_product(product_id)
    return ProductOwnerService.get_dashboard_data(product_id)


product_owner_router = Router(
    path="/admin/products",
    route_handlers=[
        list_product_decisions,
        create_product_decision,
        get_decision,
        update_decision,
        delete_decision,
        list_milestones,
        create_milestone,
        get_milestone,
        update_milestone,
        delete_milestone,
        list_milestone_projects,
        link_project,
        unlink_project,
        assign_owner,
        trigger_standup,
        meeting_history,
        get_dashboard,
    ],
)
