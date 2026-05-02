"""agents + tracing routes (track A, wave 60)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import HTTPException, NotFoundException

from app.db.owned_entities import get_for_user
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

from ..auth import Caller


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
    if caller.user_id:
        rows = get_for_user(
            "agents", caller.user_id, limit=limit, offset=offset or 0
        )
        return {"agents": rows, "total_count": len(rows)}
    return _result_or_raise(
        AgentService.list_agents(limit=limit, offset=offset or 0)
    )


@post("/", sync_to_thread=False)
def create_agent(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(
        AgentService.create_agent({k: v for k, v in (data or {}).items() if v is not None})
    )


@get("/{agent_id:str}", sync_to_thread=False)
def get_agent_detail(agent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(AgentService.get_agent_detail(agent_id))


@put("/{agent_id:str}", sync_to_thread=False)
def update_agent(
    agent_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    return _result_or_raise(
        AgentService.update_agent_data(
            agent_id, {k: v for k, v in (data or {}).items() if v is not None}
        )
    )


@delete("/{agent_id:str}", status_code=200, sync_to_thread=False)
def delete_agent(agent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(AgentService.delete_agent_by_id(agent_id))


@post("/{agent_id:str}/run", sync_to_thread=False)
def run_agent(
    agent_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    return _result_or_raise(
        AgentService.run_agent(agent_id, (data or {}).get("message", ""))
    )


@get("/{agent_id:str}/export", sync_to_thread=False)
def export_agent(agent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.export_agent_to_harness(agent_id))


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
    return {
        "traces": list_traces(
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            limit=limit,
            offset=offset,
        ),
        "total": count_traces(
            entity_type=entity_type, entity_id=entity_id, status=status
        ),
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
        end_trace_route,
        delete_trace_route,
        create_new_span,
        list_trace_spans,
        get_span_detail,
        end_span_route,
    ],
)
