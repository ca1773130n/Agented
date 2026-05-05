"""v0.7.1: admin endpoints for trigger payload events (list/get/replay)."""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import NotFoundException
from litestar.status_codes import HTTP_200_OK

from app.services import trigger_event_service
from app_litestar.auth_guards import requires_role


@get(
    "/{trigger_id:str}/events",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def list_events(trigger_id: str, limit: int = 50) -> dict[str, Any]:
    return {"events": trigger_event_service.list_for_trigger(trigger_id, limit=limit)}


@get(
    "/events/{event_id:int}",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def get_event(event_id: int) -> dict[str, Any]:
    e = trigger_event_service.get(event_id)
    if e is None:
        raise NotFoundException(detail=f"trigger_event {event_id} not found")
    return e


@post(
    "/events/{event_id:int}/replay",
    sync_to_thread=True,
    guards=[requires_role("admin")],
    status_code=HTTP_200_OK,
)
def replay_event(event_id: int) -> dict[str, Any]:
    try:
        fired = trigger_event_service.replay(event_id)
    except LookupError as exc:
        raise NotFoundException(detail=str(exc)) from exc
    return {"fired": fired}


trigger_events_router = Router(
    path="/admin/triggers",
    route_handlers=[list_events, get_event, replay_event],
)
