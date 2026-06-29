"""agents + tracing routes (track A, wave 60)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import HTTPException, NotFoundException
from litestar.response import Stream

from app.db.owned_entities import can_access
from app.db.tracing import (
    count_traces,
    create_span,
    create_trace,
    delete_trace,
    end_span,
    end_trace,
    get_span,
    get_trace,
    get_trace_stats,
    get_trace_with_spans,
    list_spans,
    list_traces,
)
from app.services.agent_service import AgentService
from app.services.skills_service import SkillsService
from app_litestar.route_helpers import clamp_limit

from ..auth import Caller
from ..list_scope import admin_or_scoped


def _result_or_raise(payload: tuple[dict, int]) -> dict:
    body, status = payload
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


# ===========================================================================
# /admin/agents/* (7 routes)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_agents(
    caller: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    return admin_or_scoped(
        caller,
        "agents",
        "agents",
        limit=limit,
        offset=offset or 0,
        all_=lambda: _result_or_raise(AgentService.list_agents(limit=limit, offset=offset or 0)),
    )


def _assert_agent_access(agent_id: str, caller: Caller) -> None:
    """Enforce per-object ownership on a single agent (IDOR, H2). Admins and the
    owner pass; legacy/unowned rows are shared. 404 on denial to avoid leaking
    which ids exist."""
    if not can_access("agents", agent_id, caller.user_id, caller.role):
        raise NotFoundException(detail="Agent not found")


@post("/", sync_to_thread=False)
def create_agent(data: dict, caller: Caller) -> dict[str, Any]:
    # Strip any client-supplied user_id; ownership is the authenticated caller.
    payload = {k: v for k, v in (data or {}).items() if v is not None and k != "user_id"}
    return _result_or_raise(AgentService.create_agent(payload, user_id=caller.user_id))


@get("/{agent_id:str}", sync_to_thread=False)
def get_agent_detail(agent_id: str, caller: Caller) -> dict[str, Any]:
    _assert_agent_access(agent_id, caller)
    return _result_or_raise(AgentService.get_agent_detail(agent_id))


@put("/{agent_id:str}", sync_to_thread=False)
def update_agent(agent_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    _assert_agent_access(agent_id, caller)
    return _result_or_raise(
        AgentService.update_agent_data(
            agent_id,
            {k: v for k, v in (data or {}).items() if v is not None and k != "user_id"},
        )
    )


@delete("/{agent_id:str}", status_code=200, sync_to_thread=False)
def delete_agent(agent_id: str, caller: Caller) -> dict[str, Any]:
    _assert_agent_access(agent_id, caller)
    return _result_or_raise(AgentService.delete_agent_by_id(agent_id))


@post("/{agent_id:str}/run", sync_to_thread=False)
def run_agent(agent_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    _assert_agent_access(agent_id, caller)
    return _result_or_raise(AgentService.run_agent(agent_id, (data or {}).get("message", "")))


@get("/{agent_id:str}/export", sync_to_thread=False)
def export_agent(agent_id: str, caller: Caller) -> dict[str, Any]:
    _assert_agent_access(agent_id, caller)
    return _result_or_raise(SkillsService.export_agent_to_harness(agent_id))


# PR-J3b: agent capability matrix backend not yet implemented. Returning 501
# matches the "Not yet enabled" banner shipped in PR-J3 (AgentCapabilityMatrix.vue).
@get("/capabilities", sync_to_thread=False)
def agent_capabilities() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


agents_router = Router(
    path="/admin/agents",
    route_handlers=[
        list_agents,
        create_agent,
        get_agent_detail,
        update_agent,
        delete_agent,
        run_agent,
        export_agent,
        agent_capabilities,
    ],
)


# ===========================================================================
# /admin/traces/* (10 routes)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_all_traces(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = clamp_limit(limit, default=100)
    return {
        "traces": list_traces(
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            limit=limit,
            offset=offset,
        ),
        "total": count_traces(entity_type=entity_type, entity_id=entity_id, status=status),
    }


@post("/", sync_to_thread=False)
def create_new_trace(data: dict) -> dict[str, Any]:
    return create_trace(
        name=(data or {}).get("name", ""),
        entity_type=(data or {}).get("entity_type"),
        entity_id=(data or {}).get("entity_id"),
        execution_id=(data or {}).get("execution_id"),
        input_data=(data or {}).get("input"),
        metadata=(data or {}).get("metadata"),
    )


@get("/stats", sync_to_thread=False)
def trace_stats(
    entity_type: Optional[str] = None, entity_id: Optional[str] = None
) -> dict[str, Any]:
    return get_trace_stats(entity_type=entity_type, entity_id=entity_id)


@get("/{trace_id:str}", sync_to_thread=False)
def get_trace_detail(trace_id: str) -> dict[str, Any]:
    trace = get_trace_with_spans(trace_id)
    if not trace:
        raise NotFoundException(detail="Trace not found")
    return trace


@get("/{trace_id:str}/stream", media_type="text/event-stream", sync_to_thread=False)
async def stream_trace(trace_id: str) -> Stream:
    """v0.5.10: SSE stream of live trace events.

    Polls the DB every 1s for span and trace state changes, emits
    diffs as SSE frames:
      - span_started: data is the full span dict
      - span_ended: data is the full span dict (status changed)
      - trace_ended: data is the trace dict; closes the stream

    Closes after the trace reaches 'completed' / 'error' status, or
    after a 10-min hard timeout, or when the client disconnects.

    The polling-loop variant is intentional for v0.5.10: keeps the
    write path (tracing.py end_span/update_span/end_trace) untouched.
    Migrate to a process-local pub/sub bus once a second consumer of
    the event stream appears.
    """

    async def event_generator():
        seen_span_ids: set[str] = set()
        span_status: dict[str, str] = {}
        deadline = asyncio.get_event_loop().time() + 600.0  # 10 min
        while True:
            trace = get_trace(trace_id)
            if trace is None:
                yield f"event: error\ndata: {json.dumps({'reason': 'not_found'})}\n\n"
                return
            spans = list_spans(trace_id)
            for s in spans:
                sid = s["id"]
                if sid not in seen_span_ids:
                    seen_span_ids.add(sid)
                    span_status[sid] = s["status"]
                    yield f"event: span_started\ndata: {json.dumps(s, default=str)}\n\n"
                elif span_status.get(sid) != s["status"]:
                    span_status[sid] = s["status"]
                    yield f"event: span_ended\ndata: {json.dumps(s, default=str)}\n\n"
            if trace["status"] in ("completed", "error"):
                yield f"event: trace_ended\ndata: {json.dumps(trace, default=str)}\n\n"
                return
            if asyncio.get_event_loop().time() > deadline:
                yield f"event: timeout\ndata: {json.dumps({'reason': 'max_duration'})}\n\n"
                return
            await asyncio.sleep(1.0)

    return Stream(event_generator(), media_type="text/event-stream")


@put("/{trace_id:str}/end", sync_to_thread=False)
def end_trace_route(trace_id: str, data: dict) -> dict[str, Any]:
    if not get_trace(trace_id):
        raise NotFoundException(detail="Trace not found")
    return end_trace(
        trace_id=trace_id,
        status=(data or {}).get("status", "ok"),
        output_data=(data or {}).get("output"),
        error_message=(data or {}).get("error_message"),
    )


@delete("/{trace_id:str}", status_code=200, sync_to_thread=False)
def delete_trace_route(trace_id: str) -> dict[str, Any]:
    if not delete_trace(trace_id):
        raise NotFoundException(detail="Trace not found")
    return {"message": f"Trace {trace_id} deleted"}


@post("/{trace_id:str}/spans", sync_to_thread=False)
def create_new_span(trace_id: str, data: dict) -> dict[str, Any]:
    if not get_trace(trace_id):
        raise NotFoundException(detail="Trace not found")
    return create_span(
        trace_id=trace_id,
        name=(data or {}).get("name", ""),
        span_type=(data or {}).get("span_type"),
        parent_span_id=(data or {}).get("parent_span_id"),
        input_data=(data or {}).get("input"),
        attributes=(data or {}).get("attributes"),
        metadata=(data or {}).get("metadata"),
    )


@get("/{trace_id:str}/spans", sync_to_thread=False)
def list_trace_spans(trace_id: str) -> dict[str, Any]:
    if not get_trace(trace_id):
        raise NotFoundException(detail="Trace not found")
    spans = list_spans(trace_id)
    return {"spans": spans, "count": len(spans)}


@get("/{trace_id:str}/spans/{span_id:str}", sync_to_thread=False)
def get_span_detail(trace_id: str, span_id: str) -> dict[str, Any]:
    span = get_span(span_id)
    if not span or span.get("trace_id") != trace_id:
        raise NotFoundException(detail="Span not found")
    return span


@put("/{trace_id:str}/spans/{span_id:str}/end", sync_to_thread=False)
def end_span_route(trace_id: str, span_id: str, data: dict) -> dict[str, Any]:
    span = get_span(span_id)
    if not span or span.get("trace_id") != trace_id:
        raise NotFoundException(detail="Span not found")
    return end_span(
        span_id=span_id,
        status=(data or {}).get("status", "ok"),
        output_data=(data or {}).get("output"),
        error_message=(data or {}).get("error_message"),
        attributes=(data or {}).get("attributes"),
    )


tracing_router = Router(
    path="/admin/traces",
    route_handlers=[
        list_all_traces,
        create_new_trace,
        trace_stats,
        get_trace_detail,
        stream_trace,
        end_trace_route,
        delete_trace_route,
        create_new_span,
        list_trace_spans,
        get_span_detail,
        end_span_route,
    ],
)
